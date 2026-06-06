---
source_of_truth:
  - task3.md
  - docs/PRD-frontend.md #(§14.4 아토믹 디자인 패턴 레이아웃)
---
## F2: Atoms

### SDD

**아토믹 규칙**: 상태·로직·API 호출 불가. Props + 렌더링만 처리.

**파일**: `src/components/atoms/Badge.tsx`
```typescript
interface BadgeProps {
  domain: string           // 단일 도메인 식별자 (예: "security", "compliance")
  colorHex?: string        // domain_registry DB에서 조회된 런타임 hex 색상값 (동적 확장)
  label?: string           // 화면 표기용 텍스트 (기본값: domain 값 그대로 사용)
  size?: "sm" | "md"
}
// 하드코딩 제거: colorHex가 주입되면 인라인 스타일로 반영, 없을 때만 fallback 기본 테마 적용
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
| --- | --- | --- | --- |
| T_F2_badge_dynamic_color | `<Badge domain="compliance" colorHex="#884488" />` | `render(...)` | 요소의 인라인 스타일 또는 스타일에 `background-color: #884488` 반영 확인 (런타임 확장 검증) |
| T_F2_badge_fallback_label | `<Badge domain="security" label="보안 메커니즘" />` | `render(...)` | `domain` 대신 명시된 `label` 텍스트("보안 메커니즘") 노출 확인 |
| T_F2_status_dot_running | `<StatusDot status="RUNNING" />` | `render(...)` | `animate-pulse` 클래스 존재 여부 검증 |
| T_F2_status_dot_done | `<StatusDot status="DONE" />` | `render(...)` | 완료 상태 디자인을 상징하는 특정 스타일/클래스 결합 확인 |
| T_F2_button_disabled | `<Button variant="primary" disabled onClick={fn}>텍스트</Button>` | `userEvent.click(...)` | 클릭 인터랙션 발생 시에도 `fn` 호출 횟수가 **0회**인지 검증 |
| T_F2_button_loading | `<Button loading variant="primary">저장</Button>` | `render(...)` | 버튼 컴포넌트 내부에 `Spinner` (또는 `data-testid="spinner"`)가 정상 주입 및 노출되는지 검증 |

### COMMIT
```
test(frontend): add atoms Badge StatusDot Button Spinner RTL tests
feat(frontend): implement atoms Badge StatusDot Button Spinner components
```