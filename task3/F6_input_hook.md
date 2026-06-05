---
source_of_truth:
  - task3.md
  - docs/PRD-domain.md #(§3.1.1 선행 파싱 레이어, §3.1.2 휴먼 인 루프 검증 정책)
---
## F6: Hook — useDocumentInput

### SDD

**파일**: `src/hooks/useDocumentInput.ts`

```typescript
interface DocumentInputState {
  urls: string[]
  prescanResult: PreScanResult | null
  confidence: number
  isScanning: boolean
  isPending: boolean    // 인터락: 수동 입력 필요 상태
  addUrl: (url: string) => void
  removeUrl: (idx: number) => void
  confirmMetadata: (meta: FormMetadata) => void
  triggerPipeline: () => Promise<string>  // session_id 반환
}

// URL 추가 시 pipelineService.prescan() 자동 호출
// confidence < 0.5 → isPending = true (인터락)
// triggerPipeline → pipelineService.trigger() 호출
```

### TDD (AAA)

파일: `src/hooks/__tests__/useDocumentInput.test.ts`

| ID | Arrange | Act | Assert |
|----|---------|-----|--------|
| T_F6_add_url | 초기 `urls=[]` | `act(() => result.current.addUrl("https://test.com"))` | `urls.length === 1` |
| T_F6_max_5_urls | `urls` 이미 5개 | `addUrl(...)` | `urls.length` 여전히 5 |
| T_F6_prescan_auto | mock prescan → `{confidence:0.9, framework:"Django"}` | `addUrl(url)` | `prescanResult.framework === "Django"`, `isPending === false` |
| T_F6_interlock | mock prescan → `{confidence:0.3}` | `addUrl(url)` | `isPending === true` |
| T_F6_trigger | `urls` 1개, `isPending=false` | `triggerPipeline()` | pipelineService.trigger 1회 호출, session_id 반환 |

### COMMIT
```
test(frontend): add useDocumentInput hook tests prescan auto-inference and interlock
feat(frontend): implement useDocumentInput with prescan auto-trigger and interlock policy
```
