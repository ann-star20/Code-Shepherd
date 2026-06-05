---
source_of_truth:
  - task3.md
  - docs/PRD-frontend.md #(§14.4 아토믹 디자인 패턴 레이아웃)
---
## F2: Atoms

### SDD

**아토믹 규칙**: 상태·로직·API 호출 불가. Props + 렌더링만.

**파일**: `src/components/atoms/Badge.tsx`
```typescript
interface BadgeProps {
  domain: ConceptDomain   // 색상 결정
  label?: string          // 기본값: domain 값 그대로
  size?: "sm" | "md"
}
// :Security → 초록 배지 / :Performance → 주황 / :both → 보라
```

**파일**: `src/components/atoms/StatusDot.tsx`
```typescript
interface StatusDotProps {
  status: StepStatus     // PENDING/RUNNING/DONE/FAILED
  label?: string
}
// RUNNING → 애니메이션 pulse / DONE → 체크 / FAILED → X
```

**파일**: `src/components/atoms/Button.tsx`
```typescript
interface ButtonProps {
  variant: "primary" | "danger" | "ghost"
  onClick: () => void
  disabled?: boolean
  loading?: boolean
  children: React.ReactNode
}
```

**파일**: `src/components/atoms/Spinner.tsx`
```typescript
interface SpinnerProps { size?: "sm" | "md" | "lg" }
```

### TDD (AAA)

파일: `src/components/atoms/__tests__/Badge.test.tsx`

| ID | Arrange | Act | Assert |
|----|---------|-----|--------|
| T_F2_badge_security | `<Badge domain="security" />` | `render(...)` | 초록 계열 클래스 포함 (`text-teal` 또는 custom) |
| T_F2_badge_both | `<Badge domain="both" label="교차" />` | `render(...)` | "교차" 텍스트 노출 |
| T_F2_status_dot_running | `<StatusDot status="RUNNING" />` | `render(...)` | `animate-pulse` 클래스 존재 |
| T_F2_status_dot_done | `<StatusDot status="DONE" />` | `render(...)` | 체크 아이콘 또는 `done` 관련 클래스 |
| T_F2_button_disabled | `<Button variant="primary" disabled onClick={fn}>텍스트</Button>` | `userEvent.click(...)` | `fn` 호출 0회 |
| T_F2_button_loading | `<Button loading>저장</Button>` | `render(...)` | Spinner 컴포넌트 렌더링됨 |

### COMMIT
```
test(frontend): add atoms Badge StatusDot Button Spinner RTL tests
feat(frontend): implement atoms Badge StatusDot Button Spinner components
```