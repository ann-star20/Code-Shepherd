# claude-requirements-1day.md — Code-Sheperd-Team UI 구현 (1~2일 소요)

> **최종 요구사항 문서**. Claude에게 직접 전달하면 1~2일 안에 완성 가능한 MVP 구현 스펙.
> 
> 출처: `code-sheperd-team-adaptation.md` 11단계 → **축약 + 명확한 입출력** 형태로 변환

---

## Executive Summary

**목표**: Code-Sheperd-Team의 `/graph` 라우트를 **5단계 지식그래프 파이프라인 UI**로 구현.  
**범위**: 필수 컴포넌트만 (atoms, 일부 molecules, 핵심 hooks, 메인 페이지).  
**완성 기준**: 
- TypeScript strict mode 통과
- `/graph` 페이지 열림 + 5단계 indicator 표시
- "시작하기" 버튼 클릭 → Step 상태 변경 + 토스트 표시

---

## 필수 파일 & 스펙

### 1️⃣ 타입 정의 (1시간)

**파일**: `frontend/src/types/graph/pipeline.ts`

```typescript
// 필수 엔드포인트
export type PipelineState = "IDLE" | "RUNNING" | "WAITING_APPROVAL" | "COMMITTING" | "FINISHED" | "ERROR";
export type StepStatus = "PENDING" | "RUNNING" | "DONE" | "FAILED";
export type StepStatuses = Record<"Input" | "Crawler" | "Extractor" | "Writer" | "Resolver", StepStatus>;

export interface PipelineContext {
  docId: string;
  sessionId: string;
  currentStep: PipelineState;
  stepStatuses: StepStatuses;
}

// Acceptance criteria:
// ✓ 5개 step이 정확히 정의됨
// ✓ 각 step이 독립적인 상태를 가짐
```

### 2️⃣ 상수 & 색상 (30분)

**파일**: `frontend/src/lib/graph/constants.ts`

```typescript
export const STEPS = [
  { name: "Input", desc: "링크 유효성 및 ETag 분석" },
  { name: "Crawler", desc: "DOM 정제" },
  { name: "Extractor", desc: "Gemini 추출" },
  { name: "Writer", desc: "DB 적재" },
  { name: "Resolver", desc: "중복 병합" },
];

export const COLORS = {
  statusPending: "#D1D5DB",
  statusRunning: "#3B82F6",
  statusDone: "#10B981",
  statusFailed: "#EF4444",
};

// Acceptance criteria:
// ✓ STEPS[i].name이 정확히 5개
// ✓ COLORS의 모든 키가 정의됨 (undefined 없음)
```

### 3️⃣ StatusDot 컴포넌트 (1시간)

**파일**: `frontend/src/components/graph/atoms/StatusDot.tsx`

**Props**:
- `status: StepStatus` (required)
- `label?: string` (optional)

**Spec**:
- PENDING → · (회색, #D1D5DB)
- RUNNING → · (파란색, #3B82F6) + `animate-pulse` CSS
- DONE → ✓ (초록색, #10B981)
- FAILED → ✕ (빨강, #EF4444)
- 사이즈: `h-2.5 w-2.5` 둥근 원

**Acceptance criteria**:
- ✓ 4가지 상태 모두 정확한 색상 + 아이콘
- ✓ RUNNING 상태에서 `animate-pulse` 작동
- ✓ TypeScript strict 통과

### 4️⃣ Button 컴포넌트 (1시간)

**파일**: `frontend/src/components/graph/atoms/Button.tsx`

**Props**:
- `variant: "primary" | "danger"` (required)
- `disabled?: boolean` (optional)
- `onClick?: () => void` (optional)
- `children: React.ReactNode` (required)

**Spec**:
- primary → 파란색(#3B82F6), 호버 시 진한 파란색
- danger → 빨강(#EF4444), 호버 시 진한 빨강
- disabled → 그레이아웃

**Acceptance criteria**:
- ✓ 2가지 variant 모두 명확한 색상 구분
- ✓ disabled 상태에서 click 무시
- ✓ Tailwind 클래스로 구현

### 5️⃣ PipelineStepIndicator (분자) (1.5시간)

**파일**: `frontend/src/components/graph/molecules/PipelineStepIndicator.tsx`

**Props**:
- `stepStatuses: StepStatuses` (required)

**Spec**:
- 5개 step을 **세로 리스트** 형태로 표시
- 각 step: `[StatusDot] Step명 — 설명`
- 현재 RUNNING인 step: 배경 밝은 파란색(bg-blue-50), 폰트 bold
- 구조:
  ```
  div (flex flex-col space-y-4)
    ├─ Step 1: StatusDot + Text
    ├─ Step 2: StatusDot + Text
    └─ ...
  ```

**Acceptance criteria**:
- ✓ 5개 step이 모두 표시됨
- ✓ RUNNING 상태 step이 시각적으로 강조
- ✓ 구조가 명확하고 읽기 쉬움

### 6️⃣ DiffSummaryCard (분자) (1시간)

**파일**: `frontend/src/components/graph/molecules/DiffSummaryCard.tsx`

**Props**:
- `newCount: number` (required)
- `updateCount: number` (required)  
- `mergeCount: number` (required)

**Spec**:
- 단순 카드 컴포넌트
- 내용: `신규 {newCount}개 · 업데이트 {updateCount}개 · 병합 {mergeCount}개`
- 배경: 흰색, 테두리, 둥근 모서리

**Acceptance criteria**:
- ✓ 3가지 카운트가 정확히 표시됨
- ✓ 포맷이 명확함

### 7️⃣ useToast 훅 (1.5시간)

**파일**: `frontend/src/hooks/graph/useToast.ts`

**API**:
```typescript
const { toasts, addToast, dismiss } = useToast()
```

**스펙**:
- `toasts`: `Array<{id: string, kind: "success"|"error"|"info", message: string}>`
- `addToast(kind, message)`: 토스트 추가
- `dismiss(id)`: 토스트 제거
- **자동 소멸**: 4초 후 자동 제거

**Acceptance criteria**:
- ✓ 토스트 추가 시 즉시 화면에 나타남
- ✓ 4초 후 자동 사라짐
- ✓ dismiss 호출 시 즉시 제거
- ✓ 중복 ID 없음 (uuid 사용 권장)

### 8️⃣ usePipelineState 훅 (1시간)

**파일**: `frontend/src/hooks/graph/usePipelineState.ts`

**API**:
```typescript
const { state, stepStatuses, updateStep } = usePipelineState()
```

**스펙**:
- `state: PipelineState` — 전체 파이프라인 상태
- `stepStatuses: StepStatuses` — 각 step 상태
- `updateStep(stepName, status)` — step 상태 업데이트
- **저장소**: localStorage에 저장 (새로고침 후에도 유지)

**Acceptance criteria**:
- ✓ 상태 변경이 즉시 반영됨
- ✓ localStorage에 저장됨 (확인: DevTools → Application → localStorage)
- ✓ 페이지 새로고침 후 상태 복구됨

### 9️⃣ KnowledgePipeline 페이지 (1.5시간)

**파일**: `frontend/src/pages/graph/KnowledgePipeline.tsx`

**구조**:
```tsx
import { usePipelineState } from '@/hooks/graph/usePipelineState'
import { useToast } from '@/hooks/graph/useToast'
import PipelineStepIndicator from '@/components/graph/molecules/PipelineStepIndicator'
import Button from '@/components/graph/atoms/Button'

export default function KnowledgePipeline() {
  const { state, stepStatuses, updateStep } = usePipelineState()
  const { toasts, addToast } = useToast()

  const handleStart = () => {
    updateStep('Input', 'RUNNING')
    addToast('info', 'Pipeline started...')
  }

  return (
    <div className="p-8">
      <h1 className="text-3xl font-bold mb-6">지식그래프 파이프라인</h1>
      
      <PipelineStepIndicator stepStatuses={stepStatuses} />
      
      <Button 
        variant="primary" 
        onClick={handleStart}
        className="mt-6"
      >
        시작하기
      </Button>

      {/* 토스트 컨테이너 */}
      <div className="fixed top-4 right-4 z-50 space-y-2">
        {toasts.map(t => (
          <div 
            key={t.id} 
            className="bg-white border rounded px-4 py-2 shadow-lg"
          >
            {t.message}
          </div>
        ))}
      </div>
    </div>
  )
}
```

**Acceptance criteria**:
- ✓ 페이지 로드 시 제목 + indicator + 버튼 표시
- ✓ "시작하기" 버튼 클릭 → step 상태 변경
- ✓ 토스트 4초 후 소멸
- ✓ TypeScript strict 통과

### 🔟 라우팅 연결 (30분)

**파일**: `frontend/src/pages/graph/index.ts`

```typescript
export { default } from './KnowledgePipeline'
```

**파일**: `frontend/src/App.tsx` (수정)

```typescript
// 기존 Placeholder 라우트 제거:
// <Route path="/graph" element={<Placeholder />} />

// 신규 라우트 추가:
import KnowledgePipeline from '@/pages/graph'
// ...
<Route path="/graph" element={<KnowledgePipeline />} />
```

**Acceptance criteria**:
- ✓ `npm run dev` 후 `http://localhost:5173/graph` 접속 가능
- ✓ 페이지 로드됨 (에러 없음)

---

## 구현 순서 (의존성 고려)

| 순서 | 파일 | 소요시간 | 의존성 |
|------|------|--------|------|
| 1 | pipeline.ts (타입) | 1h | 없음 |
| 2 | constants.ts | 0.5h | 없음 |
| 3 | StatusDot | 1h | constants.ts |
| 4 | Button | 1h | 없음 |
| 5 | PipelineStepIndicator | 1.5h | StatusDot, constants.ts |
| 6 | DiffSummaryCard | 1h | 없음 |
| 7 | useToast | 1.5h | 없음 |
| 8 | usePipelineState | 1h | pipeline.ts |
| 9 | KnowledgePipeline.tsx | 1.5h | 위 전부 |
| 10 | index.ts + App.tsx | 0.5h | KnowledgePipeline |

**총 소요시간: 9~10시간** (1일, 또는 2일 여유)

---

## 폴더 구조 (생성할 것)

```
frontend/src/
├── components/graph/
│   ├── atoms/
│   │   ├── StatusDot.tsx
│   │   ├── Button.tsx
│   │   └── Badge.tsx (선택: 나중)
│   └── molecules/
│       ├── PipelineStepIndicator.tsx
│       └── DiffSummaryCard.tsx
├── hooks/graph/
│   ├── usePipelineState.ts
│   └── useToast.ts
├── lib/graph/
│   └── constants.ts
├── pages/graph/
│   ├── KnowledgePipeline.tsx
│   └── index.ts
└── types/graph/
    └── pipeline.ts
```

---

## 최종 입력 (Claude에게 전달)

```markdown
아래 요구사항을 참고해 Code-Sheperd-Team의 /graph 페이지를 구현해줘.

### 필수 구현 항목

1. **타입 정의** (`frontend/src/types/graph/pipeline.ts`)
   - PipelineState: "IDLE" | "RUNNING" | "WAITING_APPROVAL" | "COMMITTING" | "FINISHED" | "ERROR"
   - StepStatus: "PENDING" | "RUNNING" | "DONE" | "FAILED"
   - StepStatuses: {Input, Crawler, Extractor, Writer, Resolver} 각각 StepStatus

2. **상수** (`frontend/src/lib/graph/constants.ts`)
   - STEPS 배열: 5개 step + 설명
   - COLORS 객체: status 색상 4가지

3. **StatusDot 컴포넌트** (`frontend/src/components/graph/atoms/StatusDot.tsx`)
   - Props: status (StepStatus), label (optional)
   - PENDING/RUNNING/DONE/FAILED 각각 다른 색상 + 아이콘
   - RUNNING에서 animate-pulse

4. **Button 컴포넌트** (`frontend/src/components/graph/atoms/Button.tsx`)
   - Props: variant ("primary" | "danger"), disabled, onClick, children
   - 두 가지 색상 variant

5. **PipelineStepIndicator** (`frontend/src/components/graph/molecules/PipelineStepIndicator.tsx`)
   - Props: stepStatuses
   - 5개 step을 세로 리스트로, 현재 RUNNING인 것 강조

6. **DiffSummaryCard** (`frontend/src/components/graph/molecules/DiffSummaryCard.tsx`)
   - Props: newCount, updateCount, mergeCount
   - 집계 정보 표시

7. **useToast 훅** (`frontend/src/hooks/graph/useToast.ts`)
   - API: { toasts, addToast, dismiss }
   - 4초 자동 소멸

8. **usePipelineState 훅** (`frontend/src/hooks/graph/usePipelineState.ts`)
   - API: { state, stepStatuses, updateStep }
   - localStorage 저장

9. **KnowledgePipeline 페이지** (`frontend/src/pages/graph/KnowledgePipeline.tsx`)
   - 제목 + PipelineStepIndicator + "시작하기" 버튼
   - 버튼 클릭 → step 상태 변경 + 토스트 표시

10. **라우팅** (`frontend/src/pages/graph/index.ts`, `App.tsx`)
    - /graph → KnowledgePipeline

### 완성 기준

✓ TypeScript strict mode 통과
✓ npm run dev → /graph 접속 가능
✓ "시작하기" 버튼 클릭 → step 상태 변경 + 토스트 표시
✓ localStorage에 상태 저장됨
```

---

## 제외 항목 (Phase 2에서 구현)

❌ TopologyViewer (react-force-graph)  
❌ ApprovalPanel (HITL 승인)  
❌ ConceptInspector  
❌ LogConsole (SSE)  
❌ 백엔드 API 연결  
❌ 모달들 (MetadataLearnModal, DuplicateDocumentModal)  

---

## 참고

기존 프로젝트 구조 활용:
- Tailwind CSS는 이미 셋업됨 → `className` 사용
- `@/*` 경로 alias 사용 (`@/components`, `@/hooks` 등)
- TypeScript strict mode 권장
