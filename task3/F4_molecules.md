---
source_of_truth:
  - task3.md
  - docs/PRD-frontend.md #(§3.1.2 인터락 UI 요소, §3.8 Frontend UI/UX)
---
## F4: Molecules

### SDD

**파일**: `src/components/molecules/PipelineStepIndicator.tsx`
```typescript
interface PipelineStepIndicatorProps {
  steps: PipelineStep[]   // 5단계 배열
}
// StatusDot + AgentStep 이름 텍스트 조합
// RUNNING 단계만 강조 (bold + 배경색)
```

**파일**: `src/components/molecules/MetadataForm.tsx`
```typescript
interface MetadataFormProps {
  urls: string[]
  prescanResult?: PreScanResult    // 자동 추론값 (있으면 Pre-fill)
  confidence?: number              // 추론 신뢰도 0.0~1.0
  onConfirm: (metadata: FormMetadata) => void
  onAddUrl: () => void
  onRemoveUrl: (idx: number) => void
}
// confidence >= 0.8 → "자동 추론됨 ✓" Badge
// confidence < 0.8  → "수동 입력 필요 ⚠" Badge + 필드 하이라이트
// URL 최대 5개 제한
```

**파일**: `src/components/molecules/DiffSummaryCard.tsx`
```typescript
interface DiffSummaryCardProps {
  newCount: number        // 신규 노드
  updateCount: number     // 속성 업데이트
  mergeCount: number      // SAME_AS 병합 예정
}
// "신규 N개 · 업데이트 M개 · 병합 K개" 텍스트 카드
```

### TDD (AAA)

파일: `src/components/molecules/__tests__/PipelineStepIndicator.test.tsx`

| ID | Arrange | Act | Assert |
|----|---------|-----|--------|
| T_F4_steps_render | 5단계 steps 배열 | `render(<PipelineStepIndicator steps={steps}/>)` | 5개 단계명 모두 노출 |
| T_F4_running_highlighted | `steps[2].status="RUNNING"` | `render(...)` | "Extractor" 텍스트 bold 또는 강조 클래스 |
| T_F4_meta_confidence_high | `confidence=0.9`, `prescanResult={framework:"Django"}` | `render(<MetadataForm .../>)` | "자동 추론됨" 텍스트 노출 |
| T_F4_meta_confidence_low | `confidence=0.2`, `prescanResult=undefined` | `render(<MetadataForm .../>)` | "수동 입력 필요" 텍스트 노출 |
| T_F4_url_max_5 | `urls` 길이 5 | `fireEvent.click(addUrl 버튼)` | 버튼 disabled 또는 추가 불가 |
| T_F4_diff_card | `newCount=4, updateCount=2, mergeCount=1` | `render(<DiffSummaryCard .../>)` | "4", "2", "1" 모두 노출 |

### COMMIT
```
test(frontend): add molecules PipelineStepIndicator MetadataForm DiffSummaryCard RTL tests
feat(frontend): implement molecules with atomic composition and confidence badge logic
```