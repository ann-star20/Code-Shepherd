
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