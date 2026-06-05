---
source_of_truth:
  - task3.md
  - docs/PRD-domain.md #(§2 주요 유즈케이스, §14.4 아토믹 레이어별 책임 구분)
  - docs/PRD-arch.md
---
## F12: Template + MainPage 조립

### SDD

**파일**: `src/components/templates/DashboardLayout.tsx`
```typescript
interface DashboardLayoutProps {
  sidebar: React.ReactNode     // 왼쪽: URL 입력 + 파이프라인 상태
  main: React.ReactNode        // 가운데: TopologyViewer
  inspector: React.ReactNode   // 오른쪽: ConceptInspector
}
// 3-panel 레이아웃 (CSS Grid 또는 Flexbox)
// sidebar: 고정 240px / main: flex-1 / inspector: 고정 320px
```

**파일**: `src/pages/MainPage.tsx`
```typescript
// 모든 훅 + 유기체 조립:
// - useDocumentInput → MetadataForm + 파이프라인 트리거
// - usePipelineSSE(sessionId) → PipelineStepIndicator + LogConsole
// - useGraphMerge(sessionId) → TopologyViewer
// - useStagingApproval(sessionId) → ApprovalPanel
// - selectedNode state → ConceptInspector
// - DashboardLayout으로 최종 조립
```

### TDD (AAA)

파일: `src/pages/__tests__/MainPage.test.tsx`

| ID | Arrange | Act | Assert |
|----|---------|-----|--------|
| T_F12_layout_renders | 모든 서비스 mock | `render(<MainPage/>)` | 에러 없이 렌더링 |
| T_F12_three_panels | — | `render(<DashboardLayout sidebar={<div/>} main={<div/>} inspector={<div/>}/>)` | 3개 slot DOM에 존재 |
| T_F12_trigger_flow | mock prescan + trigger | URL 입력 → Confirm 클릭 → 트리거 버튼 | pipelineService.trigger 호출 확인 |
| T_F12_node_select | mock topology + click | TopologyViewer 노드 클릭 | ConceptInspector에 노드 정보 노출 |

### COMMIT
```
test(frontend): add DashboardLayout MainPage integration assembly tests
feat(frontend): implement DashboardLayout 3-panel template and MainPage full hook composition
```
