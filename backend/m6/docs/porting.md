# porting.md — 타 프로젝트 사이드바 + 신규 페이지 이식 가이드

> 출처: `frontend/src/{pages,components,hooks,services}`, `vite.config.ts`, `backend/app/interfaces/api/*`.

## 5.1 프론트엔드 구조 (현행)

- 라우트: `App.tsx` 에 `/knowledge-pipe` 하드코딩 + `*`→리다이렉트.
- 페이지: `pages/MainPage.tsx`(약 1,700줄 모놀리식, 상태/refs 집중).
- 레이아웃: `templates/DashboardLayout.tsx`(sidebar | main | inspector 3-column).
- 핵심 컴포넌트: `PipelineStepIndicator`(5단계), `TopologyViewer`(react-force-graph-2d), `ConceptInspector`, `ApprovalPanel`, `MetadataLearnModal`, `LogConsole`.
- 훅: `usePipelineSSE`, `useStagingApproval`, `useDocumentInput`, `useGraphMerge`.
- API 클라: `services/api.ts`(`axios`, `baseURL:"/api"`), `pipelineOrchestrator/stagingService/graphService`.
- 상태관리: 전역 스토어 없음(useState/useRef 집중) → 이식 용이하나 추출 리팩터 권장.

## 5.2 백엔드 API 표면 (이식 대상 계약)

| 그룹 | 엔드포인트 |
|------|-----------|
| Documents | `POST /api/documents`, `POST /documents/check-duplicate`, `POST /documents/{doc_id}/prescan`, `POST /documents/metadata/learn` |
| Pipeline | `POST /api/pipeline/trigger`, `GET /api/pipeline/stream/{session_id}`(SSE), `POST /pipeline/{session_id}/resume` |
| Staging(HITL) | `GET /api/staging/{session_id}`, `POST .../approve`, `.../commit`, `.../reject`, `GET .../diff`, `PATCH .../nodes/{id}` |
| Graph | `GET /api/graph/topology`, `GET /api/graph/concept/{name}/code`, `GET /api/graph/domains` |

## 5.3 이식 절차 (사이드바 메뉴 + 페이지)

1. **라우트 분리**: 부모 앱 라우터에 `/<ns>/knowledge-pipeline/*` 등록, `App.tsx`의 `BrowserRouter`/자동 리다이렉트 제거.
2. **사이드바 항목 추가**: 부모 앱 네비게이션에 메뉴 엔트리 → 위 라우트로 링크.
3. **API baseURL 주입**: `services/api.ts`의 하드코딩 `"/api"` 제거 → env/context 주입(`VITE_API_BASE` 등). dev는 `vite.config.ts` proxy(`/api`→`:8001`) 참고.
4. **레이아웃 어댑트**: `DashboardLayout`을 부모 셸 안에 중첩하거나 inspector/sidebar 폭 조정.
5. **의존성 정렬**: `react-force-graph-2d`, `axios`, `react-router-dom@7`, Tailwind(빌드 설정 확인).
6. **SSE 재연결**: `usePipelineSSE` 의 EventSource 재연결/heartbeat 처리를 대상 네트워크에서 검증.

## ★ 커플링/개선 포인트

- ★ **하드코딩 라우트/baseURL**: `/knowledge-pipe`, `/api` 두 곳을 환경 주입으로 전환해야 멀티앱 이식 가능.
- ★ **모놀리식 페이지**: `MainPage` 상태를 `usePipeline()`/`useStaging()` 훅으로 추출 시 재사용·테스트성 향상.
- ★ **에러 경계**: 전역 ErrorBoundary만 존재 — 페이지 단위 격리 추가 권장.
- ★ **인증 연동**: 현재 전역 Provider 없음. 부모 앱 auth/세션 컨텍스트 주입 지점 마련 필요.
