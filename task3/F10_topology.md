---
source_of_truth:
  - task3.md
  - docs/PRD-frontend.md #(§3.9.4 가상 병합 렌더링 규칙)
---
## F10: Organisms — TopologyViewer

### SDD

**파일**: `src/components/organisms/TopologyViewer.tsx`

```typescript
interface TopologyViewerProps {
  sessionId: string | null
  onNodeClick: (node: GraphNode) => void
}
// useGraphMerge(sessionId) 내부 사용
// react-force-graph-2d 또는 react-force-graph 래퍼
// 노드 색상: getDomainColor(domain) 사용
// 노드 스타일: getNodeStyle(status, domain)
//   DRAFT → strokeDasharray, opacity 0.65
//   COMMITTED → 실선, opacity 1.0
//   REJECTED → 빨간 테두리, opacity 0.3
// SAME_AS_CANDIDATE edge → 점선 + "병합 예정" 레이블
// 노드 클릭 → onNodeClick(node) 호출
// 범례: Security(초록), Performance(주황), both(보라), DRAFT(점선)
```

### TDD (AAA)

파일: `src/components/organisms/__tests__/TopologyViewer.test.tsx`  
(react-force-graph는 Canvas 기반 → 클릭 콜백 + 데이터 로딩 검증 위주)

| ID | Arrange | Act | Assert |
|----|---------|-----|--------|
| T_F10_renders | mock graphService + stagingService | `render(<TopologyViewer sessionId="sid" onNodeClick={fn}/>)` | 에러 없이 렌더링 |
| T_F10_loading | API 응답 지연 mock | `render(...)` | Spinner 또는 로딩 텍스트 노출 |
| T_F10_node_count | mock topology 3 confirmed + mock staging 2 draft | hook 통해 merge | `useGraphMerge` 결과 nodes.length === 5 (단위 테스트) |
| T_F10_draft_style | `status="DRAFT"` 노드 | `getNodeStyle("DRAFT","security")` | `opacity===0.65` (순수 함수 검증) |

### COMMIT
```
test(frontend): add TopologyViewer organism render and node style tests
feat(frontend): implement TopologyViewer with react-force-graph virtual node preview
```
