---
source_of_truth:
  - task3.md
  - docs/PRD-domain.md # (§3.9.5 최종 승인 API 명세)
---
## F3: API 서비스 레이어

### SDD

**파일**: `src/services/api.ts`
```typescript
// Axios 인스턴스 — baseURL: /api, timeout: 10000
// 인터셉터: 401 → 로그 / 500 → 콘솔 에러
export const apiClient = axios.create({ baseURL: "/api", timeout: 10000 })
```

**파일**: `src/services/pipelineService.ts`
```typescript
export interface TriggerPipelineRequest {
  urls: string[]                // 최대 5개
  metadata: { framework?: string; version?: string; lang?: string }
}
export const pipelineService = {
  trigger: (req: TriggerPipelineRequest) => Promise<{ session_id: string }>,
  prescan: (url: string) => Promise<PreScanResult>,
  getHealth: () => Promise<{ status: string; mode: string }>,
}
```

**파일**: `src/services/stagingService.ts`
```typescript
export const stagingService = {
  getDraft:   (sessionId: string) => Promise<StagingRecord[]>,
  getDiff:    (sessionId: string) => Promise<DiffSummary>,
  approveAll: (sessionId: string) => Promise<{ approved: number }>,
  rejectAll:  (sessionId: string) => Promise<{ rejected: number }>,
  patchNode:  (sessionId: string, nodeId: string, state: "APPROVED"|"REJECTED") => Promise<void>,
}
```

**파일**: `src/services/graphService.ts`
```typescript
export const graphService = {
  getTopology: () => Promise<{ nodes: GraphNode[]; edges: GraphEdge[] }>,
}
```

### TDD (AAA)

파일: `src/services/__tests__/pipelineService.test.ts`  
(axios-mock-adapter 사용)

| ID | Arrange | Act | Assert |
|----|---------|-----|--------|
| T_F3_trigger_ok | mock `POST /api/pipeline/trigger` → `{session_id:"abc"}` | `pipelineService.trigger(...)` | resolves `{session_id:"abc"}` |
| T_F3_prescan_ok | mock `GET /api/pipeline/prescan?url=...` → `{framework:"Django"}` | `pipelineService.prescan(url)` | resolves with `framework === "Django"` |
| T_F3_get_draft | mock `GET /api/staging/sid123` → `[{id:"1",state:"DRAFT"}]` | `stagingService.getDraft("sid123")` | array length 1, `state === "DRAFT"` |
| T_F3_approve_all | mock `POST /api/staging/sid123/approve` → `{approved:3}` | `stagingService.approveAll("sid123")` | resolves `{approved:3}` |
| T_F3_topology | mock `GET /api/graph/topology` → `{nodes:[...], edges:[...]}` | `graphService.getTopology()` | `nodes` array 존재 |

### COMMIT
```
test(frontend): add service layer axios-mock unit tests pipelineService stagingService graphService
feat(frontend): implement api.ts axios instance with interceptors and service modules
```