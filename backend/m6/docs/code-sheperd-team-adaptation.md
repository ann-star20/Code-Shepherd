# code-sheperd-team-adaptation.md — Code-Sheperd-Team 프로젝트 적용 지침

> Code-Sheperd-Team의 **기존 폴더 구조를 유지**하면서 지식그래프 파이프라인 UI를 
> `frontend/src/pages/graph/` 아래에 구현하는 **실행 계획**.

---

## Context

Code-Sheperd-Team 프로젝트에 지식그래프 자동 추출 파이프라인 UI를 통합한다.
현재 `pages/graph/Placeholder.tsx` 진입점을 실제 UI로 교체하고, 기존 `components/`, `hooks/`, `contexts/` 등을 재활용한다.

---

## 1. 현재 폴더 구조 (기존 유지)

```
frontend/src/
├── App.tsx                          # 라우터 진입점
├── main.tsx
├── index.css
├── vite-env.d.ts
│
├── components/                      # 기존 공통 컴포넌트
│   ├── (existing components)
│   └── graph/                       # 🆕 지식그래프 전용 컴포넌트
│       ├── atoms/
│       ├── molecules/
│       └── organisms/
│
├── contexts/                        # 기존 React Context
│
├── hooks/                           # 기존 훅
│   └── graph/                       # 🆕 지식그래프 훅
│       ├── usePipelineSSE.ts
│       ├── useStagingApproval.ts
│       ├── useGraphMerge.ts
│       └── useToast.ts
│
├── layouts/                         # 기존 레이아웃
│
├── lib/                             # 기존 유틸리티
│
├── pages/
│   └── graph/                       # 진입점
│       ├── KnowledgePipeline.tsx    # 🆕 Placeholder 교체
│       ├── index.ts
│       └── (future subpages)
│
├── types/                           # 기존 타입
│   └── graph/                       # 🆕 지식그래프 타입
│       ├── pipeline.ts
│       ├── staging.ts
│       └── graph.ts
│
├── test/                            # 기존 테스트
│
└── (other existing files)
```

---

## 2. 신규 추가 폴더 & 파일 (최소 구성)

### 2.1 컴포넌트 계층 (components/graph/)

```
components/graph/
├── atoms/
│   ├── StatusDot.tsx
│   ├── Badge.tsx
│   └── Button.tsx
│
├── molecules/
│   ├── PipelineStepIndicator.tsx
│   ├── DuplicateDocumentModal.tsx
│   ├── DiffSummaryCard.tsx
│   └── MetadataLearnModal.tsx
│
└── organisms/
    ├── ApprovalPanel.tsx
    ├── ConceptInspector.tsx
    ├── TopologyViewer.tsx
    └── LogConsole.tsx
```

### 2.2 훅 (hooks/graph/)

```
hooks/graph/
├── useToast.ts
├── usePipelineSSE.ts
├── useStagingApproval.ts
├── useGraphMerge.ts
└── useDocumentInput.ts
```

### 2.3 타입 (types/graph/)

```
types/graph/
├── pipeline.ts         # PipelineState, StepStatus
├── staging.ts          # StagingConcept, DiffSummary
└── graph.ts            # GraphNode, GraphEdge
```

### 2.4 서비스 (lib/graph/ 또는 새로운 services/)

```
lib/graph/
├── api.ts                   # axios 인스턴스 설정
├── pipelineService.ts       # 파이프라인 API
├── stagingService.ts        # HITL API
├── graphService.ts          # 토폴로지 API
└── documentService.ts       # 문서 API
```

### 2.5 상수 (lib/graph/)

```
lib/graph/
├── colors.ts                # 색상 토큰
├── endpoints.ts             # API 경로
└── steps.ts                 # 파이프라인 5단계 정의
```

---

## 3. 실행 체크리스트 (11단계, 2~3주)

### Step 1: 준비 (1일)
```
[ ] 1.1 types/graph/ 폴더 생성 + pipeline.ts, staging.ts, graph.ts 작성
[ ] 1.2 constants 파일 작성: colors.ts (색상 토큰), steps.ts (5단계)
[ ] 1.3 pages/graph/KnowledgePipeline.tsx 스켈레톤 (상태 머신 틀만)
```

### Step 2: Atoms (2일)
```
[ ] 2.1 components/graph/atoms/StatusDot.tsx
[ ] 2.2 components/graph/atoms/Badge.tsx (DomainBadge + ActionBadge)
[ ] 2.3 components/graph/atoms/Button.tsx
[ ] 2.4 기존 Button 컴포넌트 있으면 재활용 검토
```

### Step 3: Molecules (3일)
```
[ ] 3.1 components/graph/molecules/PipelineStepIndicator.tsx
[ ] 3.2 components/graph/molecules/DuplicateDocumentModal.tsx
[ ] 3.3 components/graph/molecules/DiffSummaryCard.tsx
[ ] 3.4 components/graph/molecules/MetadataLearnModal.tsx
```

### Step 4: Organisms 1 (3일)
```
[ ] 4.1 components/graph/organisms/ApprovalPanel.tsx
[ ] 4.2 components/graph/organisms/ConceptInspector.tsx (신뢰도 바)
[ ] 4.3 components/graph/organisms/LogConsole.tsx
```

### Step 5: Organisms 2 - TopologyViewer (3일)
```
[ ] 5.1 react-force-graph-2d 설치 (package.json에 추가)
[ ] 5.2 lib/graph/nodeStyler.ts: getNodeStyle() 함수
[ ] 5.3 components/graph/organisms/TopologyViewer.tsx (기본)
[ ] 5.4 TopologyViewer: DRAFT 점선 + 범례 추가
```

### Step 6: Services & API (2일)
```
[ ] 6.1 lib/graph/api.ts: axios 인스턴스 + VITE_API_BASE
[ ] 6.2 lib/graph/{pipeline,staging,graph,document}Service.ts 구현
[ ] 6.3 types/graph/ 추가 필요 타입 정의
```

### Step 7: Hooks (2일)
```
[ ] 7.1 hooks/graph/useToast.ts (커스텀 토스트, 4초)
[ ] 7.2 hooks/graph/usePipelineSSE.ts (EventSource)
[ ] 7.3 hooks/graph/useStagingApproval.ts (HITL 상태)
[ ] 7.4 hooks/graph/useGraphMerge.ts (DRAFT 병합)
[ ] 7.5 hooks/graph/useDocumentInput.ts (URL 입력)
```

### Step 8: 레이아웃 & 페이지 조립 (2일)
```
[ ] 8.1 기존 layouts/DashboardLayout.tsx 있으면 재사용 검토
[ ] 8.2 새로운 DashboardLayout (3-column) 필요 시 components/graph/layouts/
[ ] 8.3 pages/graph/KnowledgePipeline.tsx: 전체 상태 머신 + 컴포넌트 조립
[ ] 8.4 pages/graph/index.ts: 진입점 export
```

### Step 9: 라우팅 수정 (1일)
```
[ ] 9.1 App.tsx: /graph 라우트 → pages/graph/KnowledgePipeline 연결
[ ] 9.2 기존 /graph/placeholder 제거 또는 리다이렉트
[ ] 9.3 라우터 네비게이션 테스트
```

### Step 10: 통합 테스트 (2일)
```
[ ] 10.1 API 엔드포인트 연결 확인
[ ] 10.2 파이프라인 전체 흐름: URL 입력 → Prescan → Extractor → HITL → 완료
[ ] 10.3 모바일 반응형 확인 (Tailwind)
[ ] 10.4 브라우저 호환성
```

### Step 11: 마무리 (1일)
```
[ ] 11.1 에러 메시지 및 로깅 정리
[ ] 11.2 Placeholder 완전 제거
[ ] 11.3 README 업데이트 (m5 모듈 활성화됨 표기)
```

---

## 4. 기존 Code-Sheperd-Team 구조와의 호환성

### 4.1 기존 components 재활용

```typescript
// 기존 Button이 있으면
import { Button } from '@/components/Button'  // 기존
// 지식그래프 전용 Button
import { Button as GraphButton } from '@/components/graph/atoms/Button'  // 신규

// 필요시 확장하거나, 기존 것 래핑
```

### 4.2 기존 hooks 활용

```typescript
// 기존 useContext, useState 등 활용 가능
// 신규 훅들은 hooks/graph/ 아래 분리
import { useToast } from '@/hooks/graph/useToast'
```

### 4.3 기존 contexts 연동

```typescript
// 필요 시 기존 contexts와 연동
// 예: 인증 context → API 호출 시 토큰 자동 주입
```

### 4.4 기존 lib 유틸

```typescript
// lib/graph/api.ts에서 axios 셋업
// 기존 lib의 다른 유틸(formatters 등) 재사용
import { formatDate } from '@/lib/formatters'
```

---

## 5. 환경 설정 확인

### 5.1 vite.config.ts 확인

```typescript
// 이미 있어야 함:
proxy: {
  '/api': {
    target: process.env.VITE_API_BASE || 'http://localhost:8001',
    changeOrigin: true,
  },
}
```

### 5.2 .env 파일 확인

```
VITE_API_BASE=http://localhost:8001
```

### 5.3 Tailwind CSS 확인

```
- tailwind.config.js 존재 확인
- globals.css에 Tailwind directives 확인
- 필요 시 커스텀 색상 추가
```

### 5.4 TypeScript 설정

```
- tsconfig.json의 paths 확인 (@/* alias)
- strict: true 권장
```

---

## 6. 코딩 컨벤션 (기존 프로젝트 맞춤)

### 6.1 파일 명명

```
- 컴포넌트: PascalCase (StatusDot.tsx)
- 훅: camelCase with 'use' (usePipelineSSE.ts)
- 상수: UPPER_SNAKE_CASE 또는 camelCase
- 타입/인터페이스: PascalCase (PipelineState.ts)
```

### 6.2 폴더 구조 일관성

```
- 컴포넌트: components/[feature]/[atom/molecule/organism]/
- 훅: hooks/[feature]/
- 타입: types/[feature]/
- 유틸: lib/[feature]/
```

### 6.3 import 경로 (alias 사용)

```typescript
// ✅ 좋음
import { StatusDot } from '@/components/graph/atoms/StatusDot'
import { usePipelineSSE } from '@/hooks/graph/usePipelineSSE'
import type { PipelineState } from '@/types/graph/pipeline'

// ❌ 피하기
import { StatusDot } from '../../../components/graph/atoms/StatusDot'
```

---

## 7. API 백엔드 필수 조건

### 7.1 필수 엔드포인트 (확인)

```
✓ POST   /api/documents
✓ POST   /api/documents/check-duplicate
✓ POST   /api/pipeline/trigger
✓ GET    /api/pipeline/stream/{session_id}  (SSE)
✓ GET    /api/staging/{session_id}
✓ POST   /api/staging/{session_id}/approve
✓ GET    /api/graph/topology
```

### 7.2 응답 형식 (타입 정의에 반영)

```typescript
// GET /api/pipeline/stream/{session_id}
{
  type: "step_update" | "log" | "heartbeat" | "finished",
  agent?: string,
  status?: string,
  message?: string,
  ts?: string
}

// GET /api/staging/{session_id}
{
  items: Array<{
    id: string,
    concept_name: string,
    infer_action: "NEW" | "MERGE" | "RELATED_TO",
    infer_confidence: number,
    state: "DRAFT" | "APPROVED" | "COMMITTED"
  }>
}
```

---

## 8. 분기별 마일스톤

| 분기 | 목표 | 체크리스트 |
|------|------|-----------|
| **Week 1** | 기초 설정 + Atoms | Steps 1-3 |
| **Week 2** | Molecules + Organisms | Steps 4-5 |
| **Week 3** | Services + Hooks | Steps 6-7 |
| **Week 3-4** | 통합 & 배포 | Steps 8-11 |

---

## 9. 주의사항

### 9.1 기존 코드와의 충돌

```typescript
// ❌ 피하기: 기존 components를 override
// ✅ 좋음: components/graph/ 아래 격리
```

### 9.2 SSE 버퍼링

```
nginx 프록시 사용 시:
X-Accel-Buffering: no 헤더 필수
```

### 9.3 DRAFT 그래프 렌더링

```typescript
// strokeDasharray는 CSS 불가
// Canvas API 직접 그리기 필요 (react-force-graph-2d callback)
ctx.setLineDash([5, 3]);
```

---

## 10. 예상 일정

```
시작: 2026-06-13
단계별 진행: 2~3주
완료 예상: 2026-06-27

유연성: 백엔드 API 지연 시 조정 가능
```

---

## 참고 자료

- **상세 컴포넌트**: `ui-ux-spec.md`
- **신규 프로젝트 가이드**: `frontend-implementation-guide.md`
- **기존 커밋**: Code-Sheperd-Team Git log (구조 참고)
