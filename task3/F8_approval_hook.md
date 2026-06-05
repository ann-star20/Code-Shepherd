---
source_of_truth:
  - task3.md
  - docs/PRD-domain.md #(§3.9.1 상태 정의, §3.9.3 논리적 트랜잭션 분리 흐름)
---
## F8: Hook — useStagingApproval

### SDD

**파일**: `src/hooks/useStagingApproval.ts`

```typescript
interface StagingApprovalState {
  records: StagingRecord[]
  diff: DiffSummary | null
  isLoading: boolean
  approveAll: () => Promise<void>
  rejectAll: () => Promise<void>
  patchNode: (nodeId: string, state: "APPROVED" | "REJECTED") => Promise<void>
  refresh: () => void
}

export function useStagingApproval(sessionId: string | null): StagingApprovalState
// approveAll → stagingService.approveAll() → 완료 후 useGraphMerge refresh 트리거
// rejectAll  → stagingService.rejectAll()
```

### TDD (AAA)

파일: `src/hooks/__tests__/useStagingApproval.test.ts`

| ID | Arrange | Act | Assert |
|----|---------|-----|--------|
| T_F8_load_records | mock getDraft → 3개 records | `renderHook(...)` 후 대기 | `records.length === 3` |
| T_F8_approve_all | mock approveAll → `{approved:3}` | `act(() => result.current.approveAll())` | stagingService.approveAll 1회 호출 |
| T_F8_reject_all | mock rejectAll → `{rejected:2}` | `act(() => result.current.rejectAll())` | stagingService.rejectAll 1회 호출 |
| T_F8_patch_node | mock patchNode → 200 | `act(() => result.current.patchNode("id1","APPROVED"))` | stagingService.patchNode("id1","APPROVED") 호출 |
| T_F8_null_session | `sessionId=null` | `renderHook(...)` | `records === []`, 서비스 호출 0회 |

### COMMIT
```
test(frontend): add useStagingApproval hook tests approve reject patch node
feat(frontend): implement useStagingApproval with staging CRUD and approval actions
```
