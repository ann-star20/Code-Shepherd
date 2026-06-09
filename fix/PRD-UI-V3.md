# [UI/UX 개정 명세] 1900px 상용 관제 대시보드 및 HITL 오케스트레이션 지침

본 지침은 실제 상용 모드(`production`)에서 **Human-in-the-Loop(HITL) 선행 추론 인터락**과 **단계별 비동기 응답 대기 상태(Spinner ➔ Check)가 완벽하게 작동하는지** 검증하기 위한 프론트엔드 핵심 화면 구성 지침입니다.

이 가이드를 바탕으로 `frontend/src/pages/MainPage.tsx` 또는 관련 오르가니즘 컴포넌트의 비동기 흐름을 빌드하시면 됩니다.

---

## 1. 글로벌 레이아웃 및 텍스트 스케일 규격 (1900px 해상도 특화)

* **글로벌 컨테이너 스펙**: 최대 가로폭 `max-w-[1900px]`을 강제 빌드하여 좌측 파이프라인 관제판과 우측 그래프 가시화 공간의 황금 비율을 1:2로 유지합니다.
* **타이포그래피 스케일 상향 (+3pt 반영)**:
* 대형 수집 카운터 숫자 및 메인 타이틀: `text-2xl` ➔ **`text-3xl`** (또는 `text-[27px]`)
* 컴포넌트 헤더 및 노드 인펙터 제목: `text-sm` ➔ **`text-lg`** (또는 `text-[17px]`)
* 본문 설명 및 터미널 로우 로그: `text-xs` ➔ **`text-base`** (또는 `text-[15px]`)


* **Neo4j 토폴로지 가시화 뷰어 세로 확장**: 기존 고정 높이 `h-80 (320px)` 구조에서 대규모 가상 노란 점선 노드가 병합 인입되는 공간을 확보하기 위해 **`h-[520px]` (세로 200px 추가 확장)** 사양을 필수로 적용합니다.

---

## 2. 프론트엔드 파이프라인 비동기 상태 머신 및 데이터 흐름 제어 계약

실시간 인디케이터와 스피너/체크 전환을 제어하고, **3단계 완료 전 불필요한 Mockup 데이터 렌더링 버그를 원천 차단**하기 위해 상태 머신을 고도화합니다.

### 2.1. 확장 비동기 상태 구조 명세 (`types/pipeline.ts`)

```typescript
// src/types/pipeline.ts
export type StepStatus = 'IDLE' | 'LOADING' | 'SUCCESS' | 'FAILED';

export interface StepDetail {
  id: 1 | 2 | 3 | 4 | 5;
  name: string;
  status: StepStatus;
  subText: string;
}

export interface PipelineProgress {
  currentStep: 1 | 2 | 3 | 4 | 5;
  globalState: 'IDLE' | 'RUNNING' | 'WAITING_APPROVAL' | 'ERROR' | 'FINISHED';
  1: StepDetail;
  2: StepDetail;
  3: StepDetail;
  4: StepDetail;
  5: StepDetail;
}

// Realtime Gemini Response 정형 패킷 데이터 인터페이스 수립
export interface ConceptJSONPayload {
  concept_name: string;
  concept_type: string;
  cwe_id: string | null;
  owasp_id: string | null;
  severity: 'critical' | 'high' | 'medium' | 'low';
  domains: string[];
  description_ko: string;
  aliases: string[];
  root_cause: string | null;
  affected_components: string[];
  mechanism: Array<{
    mechanism_name: string;
    code_examples: Array<{
      lang: string;
      lang_version: string | null;
      framework: string;
      framework_version: string | null;
      code: string;
      description: string;
    }>;
  }>;
  config_properties: Array<{ key: string; value: string; type: 'security' | 'tuning' }>;
}

```

### 2.2. `startPipeline` 핵심 비동기 오케스트레이션 및 데이터 락킹 흐름

#### 중요 가드레일 규칙 (Anti-Mockup Policy)

* **`stagingData` 컨텍스트 격리**: 우측의 '지식 그래프 가시화 토폴로지' 영역과 '보안 및 성능 개념 인스펙터' 패널은 파이프라인 기동 전 및 `1, 2, 3단계 진행 중`일 때 **반드시 `null` 상태를 유지**해야 합니다. 구형 모킹 잔재가 화면에 노출되는 것을 방지하기 위해 **블러 피드백 레이어링** 스켈레톤을 강제 마운트하세요.
* **데이터 해제 조건**: **3단계 Extractor Agent가 완벽한 `SUCCESS` 신호**를 반환하여 백엔드 PostgreSQL `staging_concepts` 레이어에 `DRAFT` 상태로 임시 격리 적재가 완료된 시점에만 `GET /api/staging/{session_id}` 패킷을 수신하여 락을 해제하고 화면을 깨웁니다.

---

## 3. 단계별 비동기 오케스트레이션 및 부분 재시도(Retry) 연동 흐름

### Phase 1: Input Agent & Prescan 단계

1. 유저가 링크 제출 후 트리거 시 `currentStep: 1`, `1번 단계: LOADING`으로 전환하여 **즉시 스피너를 노출**합니다.
2. `POST /api/documents/{doc_id}/prescan` API를 호출합니다. subText: "대기열 링크 해시 검사 및 도메인 분석 중..."을 매핑합니다.
3. **HITL 인터락 검증 분기**:
* **추론 성공 및 신규 도메인 없음**: 응답 수신 즉시 `1번 단계: SUCCESS` (체크 아이콘) 마킹 후 **자동으로 Phase 2(Crawler)로 연쇄 트리거**합니다.
* **미등록 신규 도메인 포획 (`DOMAIN_PENDING`)**: 파이프라인을 잠시 `WAITING_APPROVAL` 상태로 멈추고 경고 배지와 함께 **[도메인 추가 승인 HITL 게이트]** 컴포넌트를 활성화합니다. 관리자가 등록 확인을 누르면 비로소 `1번 단계: SUCCESS`로 변경되며 다음 단계(Phase 2)로 진입합니다.



### Phase 2: Crawler Agent 단계

1. `currentStep: 2`, `2번 단계: LOADING` 상태로 스피너를 돌립니다. subText: "대상 URL에서 불필요한 DOM 제거 및 핵심 본문 텍스트 추출 중..."을 출력합니다.
2. 크롤링 및 DOM 정제가 완료되어 200 OK 사인을 수신하면 `2번 단계: SUCCESS`(체크 마킹)로 치환하고 다음 단계(Phase 3)로 토스합니다.

### Phase 3: Extractor Agent 단계 (🎯 지식 온톨로지 생성 분기점)

1. `currentStep: 3`, `3번 단계: LOADING`으로 전환하여 **Gemini 대기용 스피너**를 활성화합니다.
2. subText: "${MODEL} 가동 중. 보안 메커니즘, 취약점 원인 및 설정 속성 구조화 JSON 추출 중..."을 롤링하며, 백엔드 SSE 로그가 수신될 때마다 화면 우측 상단에 실시간 토스트 알림을 연쇄적으로 팝업해 줍니다.
3. 백엔드에서 Gemini 분석 결과가 RDB 스테이징 테이블에 격리 적재(`state='DRAFT'`)되었다는 신호를 받으면 `3번 단계: SUCCESS` (체크 표시)로 변환합니다.

### Phase 4: Graph Writer Agent (🎯 가상 미리보기 및 원자적 최종 승인 게이트 활성화)

1. `currentStep: 4`, `4번 단계: LOADING` 스피너를 가동하며, subText: "추출된 JSON 데이터를 스테이징 레이어에 분리 보관 중..."을 출력한 뒤, 즉각 `4번 단계: SUCCESS`로 전환합니다.
2. **블러 락 해제 및 가상 미리보기 전개**: `GET /api/staging/{session_id}` 조회를 통해 받아온 실제 Gemini Response 리스크 데이터셋을 로드하여, 대시보드 상에 **노란색 점선 테두리(DRAFT 상태) 가상 노드로 오버레이 렌더링**해 줍니다.
3. **[🎯 원자적 최종 승인 게이트]**: 대시보드 최하단 고정 영역에 **`[✓ 최종 승인 및 영속 커밋]`** 및 **`[✗ 전체 반려 및 스테이징 폐기]`** 제어 바를 완벽하게 플로팅 노출하여 인간 관리자의 최종 물리 커밋 사인을 대기합니다.

### Phase 5: Link Resolver Agent (최종 영속화 종료)

1. 관리자가 최종 승인을 클릭하면 `currentStep: 5`, `5번 단계: LOADING` 스피너가 가동됩니다.
2. 백엔드에서 4대 마스터 커밋 규칙(RDB 마스터 UPSERT + Neo4j 물리 다중 라벨 결합 MERGE)이 원자적으로 종료되면, `5번 단계: SUCCESS` 최종 체크 마킹이 떨어집니다.
3. **[토폴로지 갱신]**: 가상 그래프 상의 주황색 점선 가상 노드들이 순식간에 견고한 도메인 컬러별 **영속 실선 노드로 교체**되며, 수집 프로세스가 공식 종료됩니다.

#### 🛠️ 중간 실패(`FAILED`) 발생 시 원자적 부분 복구 핸들링 규칙

* **인터랙션 차단**: 파이프라인 도중 에러가 전이되면 진행 중이던 스피너(`animate-spin`)를 **즉시 소거**하고, 붉은색 강렬한 **✗ 마크**를 렌더링한 후 하위 단계 스캔을 정지합니다.
* **호버 RETRY 엔진**: 관리자가 붉은색 ✗ 마크 영역에 마우스 마우스를 가져다 대면(Hover-In), 해당 아이콘이 **`[RETRY (재시도)]` 액션 버튼 레이어로 즉각 시각적 트랜스폼**됩니다.
* **부분 멱등 재시도**: 해당 버튼을 클릭하는 즉시, 백엔드에 `{resume_step: step_id}` 패킷을 전송하여 처음부터 전체 문서를 다시 긁지 않고, **실패한 해당 에이전트 단계부터 트랜잭션을 부분 재기동**시키는 예외 복구 알고리즘을 이행합니다.

---

## 4. UI 컴포넌트 마크업 및 아이콘 렌더링 지침 (`MainPage.tsx`)

텍스트 스케일이 3pt 상향 적용되고 가로 1900px 전용 그리드 확장. 그래프 영역 그리드 가로 세로 확장, 노드 원 확장
---

## 5. TDD 및 QA 테스트 하네스 Assert 명세 (품질 보증 가이드)

### T14. 실패(`FAILED`) 시 아이콘 교체 및 호버 RETRY 전환 물리 검증

* **시나리오**: 2단계 Crawler 진행 중 네트워크 장애 패킷을 모킹 주입하여 상태를 `FAILED`로 전이시킵니다.
* **Assert 1**: `progress[2].status === 'FAILED'` 인스턴스 판정 즉시, 클래스명 `animate-spin`을 가진 로딩 컴포넌트가 DOM 상에서 완전히 영속 제거되었음을 검증합니다.
* **Assert 2**: 마우스를 해당 엘리먼트에 호버인(`fireEvent.mouseEnter`) 시켰을 때, `RETRY`라는 텍스트 노드를 포함한 액션 `<button>` 태그가 활성화되어 캔버스 전면에 노출됨을Assert 검증합니다.

### T15. `stagingData` 원천 격리 가드 및 락 검증 (Anti-Mockup Guard)

* **시나리오**: `progress[3].status === 'LOADING'` 단계(Gemini 분석 중)를 시뮬레이션 기동합니다.
* **Assert 1**: 클라이언트 단의 `stagingData` 컨텍스트 상태값이 반드시 `null`임을 보증합니다.
* **Assert 2**: 우측 가시화 토폴로지 컨테이너 하위에 `3단계 Extractor 지식 스키마 구조화 추출 대기 중...` 문구의 텍스트 노드가 출력되고 있으며 블러 백드롭 스타일이 정상 레이어링 주입되어 있음을 검증합니다.
