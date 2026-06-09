실제 상용 모드(`production`)에서 **Human-in-the-Loop(HITL) 선행 추론 인터락**과 **단계별 비동기 응답 대기 상태(Spinner ➔ Check)가 완벽하게 작동하는지** 검증하기 위한 프론트엔드 핵심 화면 구성 지침입니다.

이 가이드를 바탕으로 `frontend/src/pages/MainPage.tsx` 또는 관련 오르가니즘 컴포넌트의 비동기 흐름을 빌드하시면 됩니다.

---

## 1. 프론트엔드 파이프라인 비동기 상태 머신 확장

실시간 인디케이터와 스피너/체크 전환을 무결하게 제어하기 위해, 기존 5단계 플랫 상태를 세부 비동기 상태(Sub-states)가 포함된 객체 구조로 관리해야 합니다.

```typescript
// types/pipeline.ts 또는 MainPage.tsx 내부 상태 정의 스펙
export type StepStatus = 'IDLE' | 'LOADING' | 'SUCCESS' | 'FAILED';

export interface PipelineProgress {
  currentStep: 1 | 2 | 3 | 4 | 5; //
  1: { name: 'Input Agent (Prescan)'; status: StepStatus }; //
  2: { name: 'Crawler Agent'; status: StepStatus }; //
  3: { name: 'Extractor Agent'; status: StepStatus }; //
  4: { name: 'Graph Writer Agent'; status: StepStatus }; //
  5: { name: 'Link Resolver Agent'; status: StepStatus }; //
}

```

---

## 2. `startPipeline` 핵심 비동기 오케스트레이션 흐름

실제 API 호출 모드에서 백엔드 엔드포인트(`SDD-A2-pipeline-api.md`)와 연동되는 프론트엔드의 논리적 흐름입니다.

### Phase 1: Input Agent & Prescan 단계

1. 유저가 링크 제출 후 트리거 시 `currentStep: 1`, `1번 단계: LOADING`으로 전환하여 **즉시 스피너를 노출**합니다.
2. `POST /api/documents/{doc_id}/prescan` API를 호출합니다.
   스피너 옆에 subText: "대기열 링크 해시 검사 및 도메인 분석 중..."을 매핑하여 시스템 작동 신뢰성을 제공합니다.
3. **HITL 인터락 검증 분기** : POST /api/documents/{doc_id}/prescan 결과에 따라 분기합니다.
* **추론 성공 및 신규 도메인 없음**: 응답 수신 즉시 `1번 단계: SUCCESS` (체크 아이콘) 마킹 후 **자동으로 Phase 2(Crawler)로 연쇄 트리거**합니다.
* **미등록 신규 도메인 포획 (`DOMAIN_PENDING`)**: 파이프라인을 잠시 `WAITING_APPROVAL` 상태로 멈추고 경고 배지와 함께 **[도메인 추가 승인 HITL 게이트]** 감지된 신규 도메인 데이터로 팝업/컴포넌트를 활성화합니다. 관리자가 등록 확인을 누르면 비로소 `1번 단계: SUCCESS`로 변경되며 다음 단계(Phase 2)로 진입합니다.



### Phase 2: Crawler Agent 단계

1. `currentStep: 2`, `2번 단계: LOADING` 상태로 스피너를 돌립니다.
2. subText: "대상 URL에서 불필요한 DOM(네비게이션, 푸터) 제거 및 핵심 본문 텍스트 추출 중..."을 하단에 출력하여 유저에게 작업 명세를 가독성 있게 전달
3. 백엔드에서 크롤링 및 DOM 정제가 완료되어 200 OK 사인을 RDB 로그 폴링(`GET /api/pipeline/logs/{session_id}`)을 통해 수신하면 `2번 단계: SUCCESS`(체크 마킹)로 치환하고 다음 단계(Phase 3)로 토스합니다.

### Phase 3: Extractor Agent 단계

1. `currentStep: 3`, `3번 단계: LOADING`으로 전환하여 **Gemini 대기용 스피너**를 활성화합니다.
2. 실제 상용망에서는 Gemini가 10개 이상의 복잡한 4-레이어 지식 개념과 코드 스니펫을 완벽한 한국어로 요약·추출하는 데 수십 초가 소요되므로, 유저가 이탈하지 않도록 이 단계에서 subText: "${MODEL(사용한 모델명)} 가동 중. 보안 메커니즘, 취약점 원인 및 설정 속성 구조화 JSON 추출 중..."을 롤링합니다.
[중요 이벤트 토스트 노출 (대안 2)]: 상용망 특성상 수십 초의 지연이 발생하므로, 백엔드 SSE 로그가 수신될 때마다 화면 우측 상단에 미려한 토스트 알림을 연쇄적으로 팝업해 줍니다.
토스트 예시: [Info] Gemini Extractor 분석 진입... (Tokens: 12,361) ➔ [Success] 10개 핵심 기술 개념 도출 완료.
3. 백엔드에서 Gemini 분석 결과가 RDB 스테이징 테이블에 격리 적재(`state='DRAFT'`)되었다는 응답이나 폴링 결과 신호를 받으면, 비로소 `3번 단계: SUCCESS` (체크 표시)로 변환하고 다음 단계(Phase 4)로 토스합니다.


### Phase 4: Graph Writer Agent (가상 미리보기 활성화)
currentStep: 4, 4번 단계: LOADING 스피너를 가동하며, subText: "추출된 JSON 데이터를 PostgreSQL 및 Neo4j 스테이징(DRAFT) 레이어에 분리 보관 중..."을 출력합니다.
1. Extractor 완료 체크 표시가 떨어짐과 동시에 4번 단계: SUCCESS로 변경(체크 마킹), 클라이언트 사이드 가상 그래프 병합 훅(`useGraphMerge.ts`)이 발동합니다.
2. `GET /api/staging/{session_id}` 조회를 통해 받아온 실제 리스크 데이터셋을 확정 데이터와 융합하여 운영 데이터베이스 락 없이 오직 브라우저 메모리 단에 **대시보드 상에 노란색 점선 테두리(DRAFT 상태) 가상 노드로 오버레이 렌더링**해 줍니다.
3. 트랜잭션 실행 Gate]: 대시보드 하단에 ✓ 최종 승인 및 ✗ 전체 반려 제어 바를 표출하여 인간 관리자의 최종 커밋 사인을 대기합니다.
4. 관리자는 인스펙터로 코드를 최종 검증한 뒤 `✓ 전체 승인` 버튼을 눌러 실제 DB 반영 트랜잭션을 트리거합니다.

Step 5: Link Resolver Agent (최종 영속화 종료)
관리자가 최종 승인을 클릭하면 currentStep: 5, 5번 단계: LOADING 스피너가 가동됩니다.

백엔드에서 4대 마스터 커밋 규칙(RDB 마스터 UPSERT + Neo4j 물리 다중 라벨 결합 MERGE)이 원자적으로 종료되면, 5번 단계: SUCCESS 최종 체크 마킹이 떨어집니다.

[토폴로지 갱신]: 가상 그래프 상의 주황색 점선 가상 노드들이 순식간에 견고한 도메인 컬러별 영속 실선 노드로 교체되며, 수집 프로세스가 공식 종료됩니다.

---

## 3. UI 컴포넌트 마크업 및 아이콘 렌더링 지침

`MainPage.tsx` 내부의 에이전트 상태 인디케이터 조각 루프 구성 예시입니다.

```jsx
{/* 컴포넌트 구조 스펙 가이드 */}
<div className="space-y-4">
  {steps.map((s) => {
    const isStepActive = progress.currentStep >= s.id;
    const stepStatus = progress[s.id].status;

    return (
      <div key={s.id} className="flex items-center justify-between p-3 rounded-xl border border-stone-100 bg-stone-50/50">
        <div className="flex items-center space-x-3">
          {/* 상태별 아이콘 스위칭 엔진 */}
          <div className="w-6 h-6 flex items-center justify-center">
            {stepStatus === 'LOADING' && (
              <div className="animate-spin rounded-full h-4 w-4 border-2 border-[#115E59] border-t-transparent" />
            )}
            {stepStatus === 'SUCCESS' && (
              <span className="text-emerald-600 font-bold text-sm">✓</span>
            )}
            {stepStatus === 'IDLE' && (
              <span className="w-2 h-2 rounded-full bg-stone-300"></span>
            )}
            {stepStatus === 'FAILED' && (
              <span className="text-rose-500 font-bold text-sm">✗</span>
            )}
          </div>
          
          <span className={`text-xs font-bold ${isStepActive ? 'text-stone-900' : 'text-stone-400'}`}>
            {s.name}
          </span>
        </div>

        {stepStatus === 'LOADING' && (
          <span className="text-[10px] text-amber-600 font-medium animate-pulse">
            응답 대기 중...
          </span>
        )}
      </div>
    );
  })}
</div>

```

3. 선택형 디버그 로그 서랍 (Drawer Component) 스펙
상세 런타임 로우(Raw) 로그를 추적해야 하는 시니어 엔지니어를 위해, 평소에는 감춰져 있다가 필요할 때만 슬라이딩 아웃되는 디버그 로그 서랍(Debug Drawer) 레이아웃 규격을 정의합니다.

진입점: 대시보드 좌측 파이프라인 진행 상태창 하단에 소형 [Terminal Raw Logs] 텍스트 버튼 배치.

인터랙션: 버튼 클릭 시 화면 우측에서 z-index: 50 플로팅 레이어로 검은색 테마의 로그 패널이 w-[450px] 크기로 부드럽게 슬라이드인(Slide-In) 애니메이션 연출.

기능: SSE/WebSocket으로 들어오는 원본 로우 텍스트 로그 스트림을 내부 버퍼에 누적 출력하며, Clear, Copy, Close(X) 제어 기능 제공.

4. TDD 및 QA 테스트 하네스 Assert 명세 (레이어 C·D 확장)
개편된 하이브리드 필터 및 비동기 상태 머신이 클라이언트 단에서 의도대로 오작동 없이 흐르는지 검증하기 위한 하네스 Assert 기준입니다.

T12. 비동기 단계별 Spinner ➔ Check 상태 전이 및 UI 렌더링 검증
시나리오: 파이프라인 트리거 API 송신 후 SSE 로그 패킷을 모킹 주입하여 단계별 상태를 변경.

Assert 1: progress[step].status === 'LOADING' 일 때, 브라우저 DOM 상에 클래스명 animate-spin을 포함한 Spinner 컴포넌트가 정상 존재함을 검증.

Assert 2: progress[step].status === 'SUCCESS' 로 전이되는 즉시, Spinner 컴포넌트가 소거되고 text-emerald-600 클래스를 지닌 체크 표시 마크(✓)로 교체 렌더링됨을 Assert.

Assert 3: 현재 진행 중인 단계 하단에 정의된 subText 스트링 명세가 정확히 일치하여 출력되는지 텍스트 노드 대조 검증.

T13. 가상 미리보기 오버레이 병합 데이터 정합성 검증
시나리오: useGraphMerge.ts 훅에 기 구축된 6개 확정 노드 리스트와, 이번 세션으로 유입된 Gemini 추출 결과 10개 노드 리스트를 주입.

Assert 1: 최종 클라이언트 병합 그래프 오브젝트의 총 노드 개수 nodes.length === 16 건 정합성 일치 판정.

Assert 2: 신규 유입된 10개 노드 인스턴스의 스타일 속성 값이 state: "DRAFT" 플래그를 지니고 있으며, Canvas 렌더러단에서 점선 테두리(strokeDasharray: [4, 4]) 속성을 반환함을 물리 검증.


---

### 📝 화면 개발 및 품질 검증 요약

* **스피너 인터락**: 프론트엔드가 단순히 `setTimeout`으로 도는 것이 아니라, 백엔드의 `state` 변화를 폴링하며 **실물 `response` 완료 이벤트와 아이콘(Spinner ➔ Check)이 정확히 동기화**되는지 브라우저 네트워크 탭으로 교차 검증하세요.
* **테스트 최적화**: 팩토리 모드(`APP_MODE=development`)일 때는 이 모든 과정이 `MockClient`를 타서 0.1초 만에 체크 표시로 넘어가므로, 실시간 스피너 디자인을 세부 튜닝하실 때는 일부러 코드 단에 `await asyncio.sleep(2)` 같은 임시 지연을 주어 UI 룩앤필을 검수한다.
