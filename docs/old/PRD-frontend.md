# [마스터 지침] 아토믹 디자인 및 가상 토폴로지 융합 프론트엔드 대시보드 빌드 세션

우리는 백엔드 파이프라인에서 추론·수렴된 보안/성능 지식 그래프 데이터를 관리자가 검증하고 최종 커밋하는 **Human-in-the-Loop(HITL) 관제 관제판**을 구축 중입니다. 제시된 아토믹 디자인 레이아웃 및 렌더링 계약을 엄수하여 Vite + TypeScript 환경의 프론트엔드 코어를 구현해 주세요.

## 1. 전담 구현 과제 명세

### 1.1. 가상 그래프 병합 엔진 구현 (`hooks/useGraphMerge.ts`)

* **목적**: 실제 DB(Neo4j)를 변경하지 않고, 기존 확정 토폴로지와 세션 DRAFT 데이터를 클라이언트 단에서 실시간 병합합니다.
* **데이터 흐름 및 로직**:
1. `graphService.getTopology()`와 `stagingService.getDraft(sessionId)`를 비동기로 동시 로드합니다.
2. `mergeVirtualGraph` 순수 함수를 통해 통합 데이터 구조(`nodes`, `links`)를 파생합니다.
3. **[3-Factor 매칭 렌더링 바인딩]**: 백엔드에서 판정한 하이브리드 점수를 기반으로 `nodeStyler.ts`와 연동하여 아래 시각 스타일 계약을 정확히 이행하세요.



### 1.2. 노드 상태별 시각 스타일 계약 (`utils/nodeStyler.ts`)

`react-force-graph` 렌더링 엔진 내에서 노드의 물리 상태와 메타데이터에 따라 아래와 같이 시각적 가독성을 차별화해야 합니다.

| 노드 상태 / 유형 | 테두리 및 형태 | 불투명도 (Opacity) | 특수 시각 효과 / 오버레이 |
| --- | --- | --- | --- |
| **기존 확정 노드** | 실선 (Solid) | `1.0` | 기본 도메인 컬러 범례 적용 |
| **신규 DRAFT 노드** | 점선 (`strokeDasharray`) | `0.65` (반투명) | 하이라이트 색상 강조 테두리 |
| **DRAFT ↔ 기존 중복** | 점선 (`strokeDasharray`) | `0.85` | **"병합 예정" 오버레이 배지** 노출 및 연결선 볼드 처리 |
| **거부(REJECTED) 노드** | 빨간 테두리 (Red) | `0.30` (흐리게) | 포인터 이벤트 차단 (`pointer-events-none`) |

### 1.3. 아토믹 레이어 격리 및 컴포넌트 구현

설계된 컴포넌트 트리 내에서 각 레이어의 책임 한계를 엄격히 고수하세요.

* **Atoms (`Badge`, `Button`, `Spinner`, `StatusDot`)**: 상태와 훅이 없는 순수 프리젠테이션 컴포넌트로 구현합니다. `Spinner`는 후행 기전 분석 중 코드 예제가 미등록(`length === 0`)인 상태로 인입될 때 무한 로딩 스켈레톤에 갇히지 않도록 내부 가드레일을 장착합니다.
* **Molecules (`PipelineStepIndicator`, `MetadataForm`, `DiffSummaryCard`)**: 두 개 이상의 원자를 조합하되 로컬 UI 상태만 허용합니다. `DiffSummaryCard`는 최종 승인 직전 `"신규 N개 / 속성 업데이트 M개 / 병합 K개"`의 지표를 연산하여 렌더링합니다.
* **Organisms (`TopologyViewer`, `ConceptInspector`, `LogConsole`)**: 독립 기동 가능한 UI 블록으로, 커스텀 훅(`useGraphMerge`, `useStagingApproval`)을 바인딩하여 데이터 흐름을 컴포넌트에 주입합니다. `LogConsole`은 SSE 스트림을 구독하여 파이프라인 5단계 인디케이터의 스피너를 체크(✓) 아이콘으로 동적 전환하는 `subText` 롤링 서랍으로 구현합니다.

## 2. 인터랙션 및 API 통합 계약

* **사이드 패널 인터락**: `TopologyViewer` 내의 가상 노드를 클릭하면 우측 `ConceptInspector` 패널에 상세 메타데이터(CWE, OWASP, Severity, RootCause 등)가 매핑되며, 개별 노드의 승인/거부 토글 상태가 클라이언트 뷰에 실시간 리플로우(Reflow)되어야 합니다.
* **일괄 트랜잭션 전송**: 상단 `ApprovalPanel`에서 `✓ 전체 승인` 버튼 클릭 시, `POST /api/staging/{session_id}/approve` 엔드포인트로 커밋을 요청하고 가상 노드 스타일을 실제 확정 노드 스타일(실선, opacity 1.0)로 원자적 전환 처리를 단행합니다.