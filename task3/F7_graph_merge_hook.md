---
source_of_truth:
  - task3.md
  - docs/PRD-frontend.md #(§3.9.4 프론트엔드 가상 노드 미리보기 규칙)
---
## F7: Hook — useGraphMerge

### SDD

**파일**: `src/hooks/useGraphMerge.ts`

```typescript
interface GraphMergeState {
  nodes: GraphNode[]     // 확정 + DRAFT 가상 병합 결과
  edges: GraphEdge[]
  isLoading: boolean
  refresh: () => void
}

export function useGraphMerge(sessionId: string | null): GraphMergeState

// 내부 동작 (PRD §3.9.4 & §14.4):
// 1. graphService.getTopology()  → confirmedNodes (status=COMMITTED)
// 2. stagingService.getDraft(sessionId) → draftNodes (status=DRAFT)
// 3. mergeVirtualGraph(confirmed, draft) → 병합 배열
//    - DRAFT 노드: status="DRAFT" (nodeStyler가 점선/반투명 처리)
//    - SAME_AS 후보: edge type="SAME_AS_CANDIDATE"
// DB 미접촉 — 순수 클라이언트 병합
```

**순수 함수** (테스트 용이성을 위해 훅 외부로 분리):
```typescript
// src/utils/mergeVirtualGraph.ts
export function mergeVirtualGraph(
  confirmed: GraphNode[],
  draft: StagingRecord[]
): { nodes: GraphNode[]; edges: GraphEdge[] }
```

### TDD (AAA)

파일: `src/utils/__tests__/mergeVirtualGraph.test.ts`

| ID | Arrange | Act | Assert |
|----|---------|-----|--------|
| T_F7_merge_adds_draft | confirmed 2개, draft 2개 | `mergeVirtualGraph(confirmed, draft)` | `nodes.length === 4` |
| T_F7_draft_status | draft 노드 포함 | `mergeVirtualGraph(...)` | draft 노드 `status === "DRAFT"` |
| T_F7_committed_opacity | committed 노드 스타일 | `getNodeStyle("COMMITTED", "security")` | `opacity === 1` |
| T_F7_draft_opacity | draft 노드 스타일 | `getNodeStyle("DRAFT", "security")` | `opacity === 0.65` |
| T_F7_same_as_candidate | confirmed에 `XSS`, draft에 `aliases:["Cross-Site Scripting"]` XSS 노드 | `mergeVirtualGraph(...)` | edge with `type="SAME_AS_CANDIDATE"` 존재 |
| T_F7_no_session | `sessionId=null` | `renderHook(() => useGraphMerge(null))` | `nodes` = confirmed 노드만 |

### COMMIT
```
test(frontend): add mergeVirtualGraph pure function unit tests same-as detection
test(frontend): add useGraphMerge hook tests with confirmed and draft merge
feat(frontend): implement mergeVirtualGraph utility and useGraphMerge hook
```
