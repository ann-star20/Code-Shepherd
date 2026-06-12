# pipeline.md — 자동 지식그래프 구축 파이프라인 지침

> 출처: `backend/app/worker/tasks.py`, `interfaces/api/{pipeline,staging,prescan}.py`. Celery+Redis 비동기 체인.

## 4.1 5단계 라이프사이클

### 1) Prescan (사전 탐색 및 중복 검증)
- URL 패턴 → `framework_metadata`(DB 주도 정규식) 매칭 + HTML 메타 추론 → `framework/lang/version/infer_confidence`.
- ETag/`content_hash(CHAR8)` 중복 검증. 신규/미탐지 도메인 → **DOMAIN_PENDING HITL 인터락**.
- 산출: `knowledge_document` 레코드(`state=PENDING`).

### 2) Crawling (원시 수집·정규화)
- `crawl_task` → `state=CRAWLING`. DOM 정제·텍스트 추출·스마트 청킹 → `extract_task.delay()` 체인.

### 3) Extract (AI 추출 + 다차원 임베딩)
- `extract_task` → `EXTRACTING`. `USE_REAL_LLM`=true 시 `GeminiClient`, 아니면 Mock.
- 4종 컨셉 + `domains[]` JSON 추출 → `write_staging_draft()`로 DRAFT 적재 → `EXTRACTED`.
- 컨셉별 `compute_resolve_score()` 사전 산출 → `infer_action/infer_confidence` 저장(★ 컴포넌트 점수는 0.0, schema.md 참조).

### 4) HITL (Human-in-the-Loop 스테이징·검증)
- 가상 노드 미리보기(`GET /api/staging/{session_id}` + `/api/graph/topology` 클라 병합 렌더).
- `approve`(DRAFT→APPROVED, `SELECT FOR UPDATE SKIP LOCKED`) / `reject` / 개별 `PATCH nodes/{id}`.

### 5) Write Graph & Resolve (하이브리드 영속화·관계 병합)
- `write_graph_task` → APPROVED 순회 → `writer.write_with_precomputed()` → Resolver 분기(MERGE/RELATED_TO/NEW) → `COMMITTED`.
- 반환 요약: `{"MERGE":n,"RELATED_TO":n,"NEW":n}`.

## SSE 이벤트 타입 (단일 채널 `/api/pipeline/stream/{session_id}`)

```json
{"type":"connected"} {"type":"log","message":"...","ts":"..."}
{"type":"step_update","agent":"Extractor","status":"SUCCESS"}
{"type":"heartbeat"} {"type":"finished"}
```
- 헤더 `X-Accel-Buffering: no`(프록시 버퍼링 우회).

## ★ 버그 방지 및 개선 요건 (Pipeline 데드락)

- ★ **락 경합**: 다중 워커 동시 승인/커밋은 `SKIP LOCKED`로 비차단 처리 — 전역 `FOR UPDATE` 회피.
- ★ **데드락 방지**: PG(staging)→Neo4j 쓰기 순서 고정. 두 DB 교차 트랜잭션 시 동일 순서 유지.
- ★ **FAILED 재진입**: `503/UNAVAILABLE`(LLM) 등 실패 시 `state=FAILED` + 세션 `staging/logs` 클린업 후 `/resume` 또는 PENDING 리셋(부분 노드 잔존 금지).
- ★ **체인 멱등성**: 태스크 재시도 시 `MERGE` 자연키로 중복 노드 미생성 보장.
