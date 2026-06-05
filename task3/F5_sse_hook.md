---
source_of_truth:
  - task3.md
  - docs/PRD-domain.md #(§3.7 태스크 상태 관리, §3.8 실시간 런타임 로그)
---
## F5: Hook — usePipelineSSE

### SDD

**파일**: `src/hooks/usePipelineSSE.ts`

```typescript
interface PipelineSSEState {
  steps: PipelineStep[]        // 5단계 현재 상태
  logs: string[]               // 누적 로그 메시지
  isConnected: boolean
}

export function usePipelineSSE(sessionId: string | null): PipelineSSEState
// sessionId가 null이면 SSE 연결 안 함
// EventSource("/api/pipeline/stream/{sessionId}")
// event.type === "step_update" → steps 갱신
// event.type === "log"         → logs 추가
// 컴포넌트 언마운트 시 EventSource.close() 호출 (메모리 누수 방지)
```

### TDD (AAA)

파일: `src/hooks/__tests__/usePipelineSSE.test.ts`  
(MSW 또는 EventSource Mock 사용)

| ID | Arrange | Act | Assert |
|----|---------|-----|--------|
| T_F5_no_session | `sessionId=null` | `renderHook(() => usePipelineSSE(null))` | `isConnected === false`, `logs.length === 0` |
| T_F5_log_appended | SSE mock → `{type:"log", data:"[Crawler] 완료"}` | hook 렌더 + 이벤트 발행 | `logs` 배열에 해당 메시지 포함 |
| T_F5_step_update | SSE mock → `{type:"step_update", data:{agent:"Crawler",status:"DONE"}}` | hook 렌더 + 이벤트 발행 | `steps[1].status === "DONE"` |
| T_F5_cleanup | sessionId 변경 | `rerender({ sessionId: "new" })` | 이전 EventSource close 호출됨 |

### COMMIT
```
test(frontend): add usePipelineSSE hook tests with SSE mock event simulation
feat(frontend): implement usePipelineSSE with EventSource step update and log accumulation
```
