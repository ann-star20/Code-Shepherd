# frontend-implementation-guide.md — 새 프로젝트 UI 신규 구현 가이드

> 빈 React 프로젝트에서 지식그래프 파이프라인 UI를 **처음부터 구현**할 때 따를 완벽한 가이드.
> 상세 컴포넌트 스니펫은 `ui-ux-spec.md` 참조.

---

## Context

새 프로젝트에 지식그래프 자동 추출 파이프라인의 **완전한 UI/UX**를 구축한다.
5단계 파이프라인(Input→Crawler→Extractor→Writer→Resolver) 상태 추적, HITL 승인 게이트, 3-Layer 토폴로지 시각화, 실시간 로그 스트림까지 통합.

---

## 1. 기술 스택 & 의존성

### 1.1 Core Framework
```json
{
  "dependencies": {
    "react": "^18.3",
    "react-dom": "^18.3",
    "react-router-dom": "^7.0",
    "typescript": "^5.3",
    "axios": "^1.6",
    "tailwindcss": "^4.0"
  },
  "devDependencies": {
    "vite": "^5.0",
    "@vitejs/plugin-react": "^4.2",
    "tailwindcss": "^4.0",
    "autoprefixer": "^10.4"
  }
}
```

### 1.2 그래프 시각화
```json
{
  "react-force-graph-2d": "^1.73.0"
}
```

### 1.3 선택사항 (아직 추가 권고 아님)
- 상태관리: Zustand / Jotai (필요 시)
- 폼 검증: React Hook Form (필요 시)
- 알림: Toast 라이브러리 대신 커스텀 구현 권고

---

## 2. 프로젝트 폴더 구조

```
src/
├── pages/
│   └── graph/
│       └── Placeholder.tsx      #  우리 기능의 메인 페이지 진입점
│
├── components/
│   # 🚨 기존 컴포넌트(ChatBot, PipelineFlow 등)는 절대 건드리지 않음
│   # 🎯 이름 충돌을 100% 방지하는 파이프라인 전용 UI 컴포넌트 플랫 배치
│   ├── GraphStatusDot.tsx              # 파이프라인 단계 상태 점
│   ├── GraphBadge.tsx                  # 도메인/infer_action 배지
│   ├── GraphPipelineStepIndicator.tsx  # 5단계 진행 표시 바
│   ├── GraphDuplicateDocumentModal.tsx # 중복 감지 경고 팝업
│   ├── GraphDiffSummaryCard.tsx        # 스테이징 데이터 집계 카드
│   ├── GraphMetadataLearnModal.tsx     # HITL 메타 데이터 보정 모달
│   ├── GraphApprovalPanel.tsx          # HITL 전체 승인/거부 제어 패널
│   ├── GraphConceptInspector.tsx       # 우측 지식 인스펙터 패널
│   ├── GraphTopologyViewer.tsx         # 2D Canvas 기반 네트워크 시각화 뷰어
│   ├── GraphLogConsole.tsx             # 실시간 SSE 롤링 터미널 로그 콘솔
│   └── GraphPipelineContainer.tsx      # DashboardLayout 구조를 흡수한 3-Column 셸 컨테이너
│
├── hooks/
│   # 🎯 우리 기능만을 제어하는 격리형 커스텀 훅 레이어
│   ├── useGraphToast.ts                # 4초 자동 소멸형 알림 훅
│   ├── useGraphPipelineSSE.ts          # SSE 실시간 로그 스트림 구독 훅
│   ├── useGraphStagingApproval.ts      # HITL 상태 머신 트랜잭션 관리 훅
│   ├── useGraphMerge.ts                # DRAFT 상태 노드 가상 병합 로직 훅
│   └── useGraphDocumentInput.ts        # 수집 URL 입력 및 검증 제어 훅
│
├── lib/
│   # 🚨 services/ 폴더를 새 프로젝트의 src/lib/ 통합 규칙으로 전면 전환
│   ├── api.ts                          # 부모 앱 공통 Axios 베이스 인스턴스
│   ├── graphPipelineApi.ts             # 🎯 파이프라인 기능 4대 서비스 계약 통합 API 파일
│   └── graphFormatters.ts              # 노드 스타일링, 날짜, 신뢰도 포매팅 유틸
│
└── types/
    └── graphPipeline.ts                # 🎯 파이프라인 상태 머신 및 토폴로지 Type 정의 단일화
```

---

## 3. 초기 설정

### 3.1 package.json 스크립트

```json
{
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview",
    "type-check": "tsc --noEmit"
  }
}
```

### 3.2 vite.config.ts

```typescript
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_BASE || 'http://localhost:8001',
        changeOrigin: true,
      },
    },
  },
})
```

### 3.3 tsconfig.json

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "jsx": "react-jsx",
    "module": "ESNext",
    "skipLibCheck": true,
    "strict": true,
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"]
    }
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

### 3.4 tailwind.config.js

```javascript
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // 도메인 색상은 constants/colors.ts에서 import
      },
      animation: {
        'pulse-custom': 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
    },
  },
  plugins: [],
}
```

### 3.5 .env.example

```
# API 설정
VITE_API_BASE=http://localhost:8001

# 선택사항
VITE_APP_NAME=Knowledge Pipeline
VITE_LOG_LEVEL=info
```

---

## 4. 단계별 구현 로드맵

### Phase 1: 기초
```
[ ] 1. 프로젝트 초기화 (vite, tailwind, typescript 설정)
[ ] 2. atoms: StatusDot, Badge, Button 구현
[ ] 3. constants/colors.ts: 색상 토큰 정의
[ ] 4. types/ 폴더: 기본 인터페이스 정의
[ ] 5. 라우터 설정: KnowledgePipelinePage 라우트 등록
```

### Phase 2: 컴포넌트 기초층
```
[ ] 6. molecules: PipelineStepIndicator 구현
[ ] 7. molecules: DuplicateDocumentModal 구현
[ ] 8. molecules: DiffSummaryCard 구현
[ ] 9. molecules: MetadataLearnModal 구현
[ ] 10. DashboardLayout.tsx: 3-column 레이아웃
```

### Phase 3: 고수준 컴포넌트
```
[ ] 11. organisms: ApprovalPanel 구현
[ ] 12. organisms: ConceptInspector 구현 (신뢰도 바 포함)
[ ] 13. organisms: LogConsole 구현 (자동 스크롤)
[ ] 14. organisms: TopologyViewer 구현 (react-force-graph-2d)
        - DRAFT: strokeDasharray 점선 + 0.65 opacity
        - MERGE_PENDING: 보라 링
        - COMMITTED: 실선, 1.0 opacity
        - 범례 (좌하단 고정)
```

### Phase 4: 상태관리 & API
```
[ ] 15. hooks/useToast.ts: 커스텀 토스트 (4초 자동 소멸)
[ ] 16. hooks/usePipelineSSE.ts: EventSource 구독
[ ] 17. hooks/useStagingApproval.ts: HITL 상태
[ ] 18. hooks/useGraphMerge.ts: DRAFT 노드 병합 로직
[ ] 19. services/api.ts: axios 인스턴스 + VITE_API_BASE
[ ] 20. services/{pipeline,staging,graph,document}Service.ts
```

### Phase 5: 페이지 조립
```
[ ] 21. PipelineContainer.tsx: 전체 상태 머신
[ ] 22. KnowledgePipelinePage.tsx: 라우트 진입점
[ ] 23. App.tsx: 라우터 설정 (부모 앱과 호환)
[ ] 24. SSE 실시간 업데이트 흐름 검증
```

### Phase 6: 통합 & 테스트
```
[ ] 25. API 엔드포인트 연결 테스트
[ ] 26. 파이프라인 시작 → 완료까지 E2E 플로우
[ ] 27. 모바일 반응형 확인 (320px, 768px, 1440px)
[ ] 28. 브라우저 호환성 (Chrome, Firefox, Safari)
```

---

## 5. 상태 머신 & 데이터 흐름

### 5.1 파이프라인 상태 머신

```typescript
// types/pipeline.ts
type PipelineState =
  | "IDLE"              // 초기, URL 입력 대기
  | "RUNNING"           // 진행 중
  | "WAITING_APPROVAL"  // HITL 게이트
  | "COMMITTING"        // 최종 적재 중
  | "FINISHED"          // 완료
  | "ERROR";            // 실패

type StepStatus = "PENDING" | "RUNNING" | "DONE" | "FAILED";
type StepStatuses = Record<"Input"|"Crawler"|"Extractor"|"Writer"|"Resolver", StepStatus>;

interface PipelineContext {
  docId: string;
  sessionId: string;
  currentStep: PipelineState;
  stepStatuses: StepStatuses;
  toasts: ToastItem[];
  logs: string[];
  isDraft: boolean;
  approvalDiff: DiffSummary | null;
  selectedNode: GraphNode | null;
}
```

### 5.2 SSE 이벤트 바인딩

```typescript
// hooks/usePipelineSSE.ts
source.onmessage = (e: MessageEvent) => {
  const payload = JSON.parse(e.data);
  
  switch (payload.type) {
    case "step_update":
      // StepStatuses 갱신 → PipelineStepIndicator 자동 반영
      break;
    case "log":
      // LogConsole.logs 추가 → 자동 스크롤
      break;
    case "finished":
      // pipelineState = "FINISHED" → ApprovalPanel 활성화
      break;
  }
};
```

---

## 6. API 서비스 통합

### 6.1 서비스 계층 구조

```typescript
// services/api.ts
const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '/api',
  timeout: 10000,
});

// services/pipelineService.ts
export async function triggerPipeline(docId: string) {
  return apiClient.post('/pipeline/trigger', { doc_id: docId });
  // 반환: { session_id, message }
}

export function subscribePipelineSSE(sessionId: string) {
  return new EventSource(`/api/pipeline/stream/${sessionId}`);
}

// services/stagingService.ts
export async function getStagingDraft(sessionId: string) {
  return apiClient.get(`/staging/${sessionId}`);
  // 반환: { items: StagingConcept[] }
}

export async function approveStagingAll(sessionId: string) {
  return apiClient.post(`/staging/${sessionId}/approve`);
}

// services/graphService.ts
export async function getGraphTopology() {
  return apiClient.get('/graph/topology');
  // 반환: { nodes: GraphNode[], edges: GraphEdge[] }
}

// services/documentService.ts
export async function checkDuplicate(url: string) {
  return apiClient.post('/documents/check-duplicate', { url });
  // 반환: { is_duplicate, doc_id }
}
```

### 6.2 필수 Backend API Endpoints

```
POST   /api/documents                    — URL 등록
POST   /api/documents/check-duplicate    — 중복 검사
POST   /api/documents/{doc_id}/prescan   — 프레임워크 추론
POST   /api/documents/metadata/learn     — HITL 메타 학습

POST   /api/pipeline/trigger             — 파이프라인 시작
GET    /api/pipeline/stream/{session_id} — SSE (text/event-stream)

GET    /api/staging/{session_id}         — DRAFT 목록
POST   /api/staging/{session_id}/approve — 전체 승인
POST   /api/staging/{session_id}/commit  — 최종 적재
POST   /api/staging/{session_id}/reject  — 전체 거부
GET    /api/staging/{session_id}/diff    — 변경 요약

GET    /api/graph/topology               — 토폴로지 (COMMITTED 노드)
GET    /api/graph/concept/{name}/code    — 코드 예제
```

---

## 7. 구현 체크포인트

### 7.1 각 단계 마다 검증

**Phase 1 완료 후:**
- TypeScript 에러 없음 (`npm run type-check`)
- 색상 토큰 정의 확인

**Phase 2 완료 후:**
- 5단계 indicator 화면 표시 (정적)
- 모달 2개(duplicate, metadata) 팝업 테스트

**Phase 3 완료 후:**
- 토폴로지 그래프 렌더링 (샘플 데이터)
- DRAFT 노드 점선 표시 확인
- 신뢰도 바 (0~100%) 표시

**Phase 4 완료 후:**
- 토스트 4초 소멸 검증
- SSE 연결 (console.log로 이벤트 확인)
- API 호출 (Network 탭 확인)

**Phase 5 완료 후:**
- Full E2E: URL 입력 → Prescan → HITL 게이트 → 승인 → 완료

---

## 8. 주의사항 & 트러블슈팅

### 8.1 그래프 렌더링
- **DRAFT 점선**: `strokeDasharray`는 CSS 불가, Canvas API 직접 그리기 필요
  ```javascript
  // react-force-graph-2d nodeCanvasObject 콜백에서
  ctx.setLineDash([5, 3]);  // 점선 패턴
  ```

### 8.2 SSE 프록시
- nginx 사용 시 반드시 헤더 추가:
  ```
  X-Accel-Buffering: no
  ```
  없으면 백엔드 로그가 버퍼링되어 실시간 전달 안 됨.

### 8.3 VITE_API_BASE
- `.env` 파일 명시적 로드 필요:
  ```typescript
  // vite.config.ts
  import { loadEnv } from 'vite'
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  ```

### 8.4 TypeScript 엄격 모드
- `strict: true` 권장 → 컴포넌트 props 타입 정의 강제
- 샘플:
  ```typescript
  interface StatusDotProps {
    status: StepStatus;
    label?: string;
  }
  ```

---

## 9. 다음 단계

완성 후 다른 프로젝트에 **이식**하려면:
1. `porting.md` 참고 — 라우트 분리, API baseURL 주입
2. 모든 `/api` 하드코딩 제거 → env 주입
3. 부모 앱 레이아웃에 DashboardLayout 중첩

---

## 부록: 색상 토큰 한눈에

| 용도 | 색상값 | Tailwind |
|------|--------|----------|
| 도메인-security | #1D9E75 | teal-600 |
| 도메인-performance | #BA7517 | amber-700 |
| 도메인-both | #534AB7 | purple-600 |
| Status-PENDING | #D1D5DB | gray-300 |
| Status-RUNNING | #3B82F6 | blue-500 |
| Status-DONE | #10B981 | green-500 |
| Status-FAILED | #EF4444 | red-500 |
| Toast-success | #10B981 | emerald-600 |
| Toast-error | #EF4444 | rose-600 |
| Severity-critical | #DC2626 | red-600 |
| Severity-high | #F97316 | orange-500 |
| Severity-medium | #EAB308 | yellow-500 |
| Severity-low | #16A34A | green-600 |
