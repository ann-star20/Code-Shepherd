---
source_of_truth:
  - task3.md
  - docs/PRD-frontend.md #(§3.8 실시간 런타임 로그)
---
## F9: Organisms — LogConsole, ApprovalPanel

### SDD

**파일**: `src/components/organisms/LogConsole.tsx`
```typescript
interface LogConsoleProps {
  logs: string[]          // usePipelineSSE에서 전달
  isConnected: boolean
}
// 고정 높이 스크롤 콘솔 (최신 로그가 아래)
// monospace 폰트, 배경 어두운 색
// isConnected=false → "연결 끊김" 상태 표시
// 자동 스크롤: 새 로그 추가 시 맨 아래로
```

**파일**: `src/components/organisms/ApprovalPanel.tsx`
```typescript
interface ApprovalPanelProps {
  sessionId: string | null
  onApproveAll: () => void
  onRejectAll: () => void
  diff: DiffSummary | null
  isLoading: boolean
}
// DiffSummaryCard + 전체 승인·거부 버튼
// isLoading → 버튼 disabled + Spinner
// diff=null → "로딩 중..." 표시
```

### TDD (AAA)

파일: `src/components/organisms/__tests__/LogConsole.test.tsx`

| ID | Arrange | Act | Assert |
|----|---------|-----|--------|
| T_F9_logs_rendered | `logs=["[Crawler] 완료", "[Extractor] 시작"]` | `render(<LogConsole logs={logs} isConnected={true}/>)` | 두 메시지 모두 DOM에 노출 |
| T_F9_disconnected | `isConnected=false` | `render(...)` | "연결 끊김" 또는 상태 표시 노출 |
| T_F9_approval_panel_buttons | `diff={newCount:4}` | `render(<ApprovalPanel .../>)` | "전체 승인", "전체 거부" 버튼 노출 |
| T_F9_approve_clicked | mock `onApproveAll` | `userEvent.click(승인 버튼)` | `onApproveAll` 1회 호출 |
| T_F9_loading_disables | `isLoading=true` | `render(...)` | 버튼 disabled + Spinner 노출 |

### COMMIT
```
test(frontend): add LogConsole ApprovalPanel organism RTL tests
feat(frontend): implement LogConsole auto-scroll SSE console and ApprovalPanel with diff summary
```
