---
source_of_truth:
  - task3.md
  - docs/PRD-frontend.md #(§3.8 컨셉 인스펙터 패널 필터링)
---
## F11: Organisms — ConceptInspector

### SDD

**파일**: `src/components/organisms/ConceptInspector.tsx`

```typescript
interface ConceptInspectorProps {
  node: GraphNode | null
  sessionId: string | null
  onApprove: (nodeId: string) => void
  onReject: (nodeId: string) => void
  onClose: () => void
}
// node=null → "노드를 클릭하세요" 안내
// node.status="COMMITTED" → 승인/거부 버튼 숨김 (읽기 전용)
// node.status="DRAFT" → 개별 승인·거부 버튼 노출
// 필드 표시: name, domain Badge, cwe_id, severity, description_ko, aliases, tags
// severity에 따른 색상: critical=빨강, high=주황, medium=노랑, low=초록
```

### TDD (AAA)

파일: `src/components/organisms/__tests__/ConceptInspector.test.tsx`

| ID | Arrange | Act | Assert |
|----|---------|-----|--------|
| T_F11_null_node | `node=null` | `render(<ConceptInspector node={null} .../>)` | "노드를 클릭하세요" 안내 텍스트 |
| T_F11_committed_readonly | `node.status="COMMITTED"` | `render(...)` | 승인·거부 버튼 없음 |
| T_F11_draft_buttons | `node.status="DRAFT"` | `render(...)` | "승인", "거부" 버튼 모두 노출 |
| T_F11_approve_click | mock `onApprove` | `userEvent.click(승인 버튼)` | `onApprove(node.id)` 1회 호출 |
| T_F11_severity_critical | `node.severity="critical"` | `render(...)` | 빨강 계열 클래스 또는 텍스트 |
| T_F11_aliases | `node.aliases=["Cross-Site Scripting","XSS"]` | `render(...)` | 두 alias 모두 노출 |
| T_F11_domain_badge | `node.domain="both"` | `render(...)` | Badge 컴포넌트 domain="both" props |

### COMMIT
```
test(frontend): add ConceptInspector organism RTL tests draft committed readonly severity
feat(frontend): implement ConceptInspector side panel with approval toggle and field display
```
