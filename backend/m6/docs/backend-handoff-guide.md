# backend-handoff-guide.md — 신규 세션 백엔드 파이프라인 구현 핸드오프

> 목적: 다른 프로젝트(또는 새 Claude 세션)에서 Code-Shepherd의 5단계 지식그래프 파이프라인
> 백엔드(Celery + FastAPI + PostgreSQL + Neo4j)를 처음부터 구현할 때, **한 번의 프롬프트**로
> 충분한 컨텍스트를 전달하기 위한 패키지. "한 번에 전부 주지 말 것" 원칙에 따라
> Phase A(DB 스키마)는 별도 세션으로 분리되어 있다고 가정한다 — 이 가이드는 **Phase B(파이프라인 백엔드)** 전용.

## A. 첨부 지침서 (전문, 이 순서로 붙여넣기)

새 세션 프롬프트 본문에 아래 3개 파일의 **전문**을 이 순서로 붙여넣는다:

1. `docs/schema.md` — 4-Layer 온톨로지, PostgreSQL DDL(vector(1024), HNSW), Neo4j 제약. (Phase A에서 이미 구현됐다면 스키마 정합성 확인용으로만 첨부)
2. `docs/idempotency.md` — MERGE/`apoc.coll.toSet` 멱등 갱신, 3-Factor 유사도(0.4/0.3/0.3, 0.88/0.72), Centroid Shifting, CodeExample `unq_id`.
3. `docs/pipeline.md` — 5단계 라이프사이클(Prescan→Crawl→Extract→HITL→Write&Resolve), SSE 이벤트, Extract 단계 LLM/임베딩 세부사항(★ 본 보강 포함).

## B. 참고 소스 코드 (구현 레퍼런스로 함께 전달)

지침서는 "무엇을/왜"를 설명하고, 아래 소스는 "어떻게"의 실제 구현 패턴을 보여준다.
새 프로젝트의 디렉토리 구조가 다르더라도 **로직과 쿼리 패턴**을 그대로 포팅한다.

| 파일 | 역할 |
|------|------|
| `backend/app/domain/models.py` | 4-Layer 스키마(`ConceptExtractionSchema`, `MechanismIn`, `PropertyIn`, `CodeExampleIn`), snake_case 정규화, 구형→신형 필드 수렴 |
| `backend/app/worker/tasks.py` | Celery 5단계 체인(`crawl_task`→`extract_task`→`write_graph_task`), 상태 전이(`_set_state`), 로그(`_log`), FAILED 클린 리부팅 |
| `backend/app/infrastructure/graph/hybrid_resolver.py` | 3-Factor 점수(Jaro-Winkler/Name Cosine/Desc Cosine), `MergeAction`(MERGE/RELATED_TO/NEW), `_do_merge` centroid shifting |
| `backend/app/infrastructure/graph/neo4j_service.py` | `GraphWriterService` — `write_with_precomputed`/`write`, domain→label 매핑(`{"security":"Security","performance":"Performance"}`), NEW/RELATED_TO 시 `_upsert_pg` |
| `backend/app/adapters/db/neo4j_repo.py` | `MERGE` Cypher, `apoc.coll.toSet`, `apoc.create.addLabels`, CodeExample `unq_id` 적재, `get_topology`/`get_concept_code` |
| `backend/app/infrastructure/llm/factory.py` | `create_llm_client`(APP_MODE별 GeminiClient/MockClient), `create_embedding_client`(BgeEmbeddingClient 싱글톤) |
| `backend/app/interfaces/api/documents.py` | `POST /api/documents`(배치 1-5, `_build_doc_id`, FAILED 클린 리부팅), `POST /check-duplicate` |
| `backend/app/interfaces/api/prescan.py` | `POST /{doc_id}/prescan`(DB 주도 `framework_metadata.url_patterns` 정규식 매칭, `CONFIDENCE_AUTO_THRESHOLD=0.8`), `POST /metadata/learn` |
| `backend/app/interfaces/api/pipeline.py` | `POST /trigger`, `GET /stream/{session_id}`(SSE, `pipeline_logs`+`knowledge_documents.state` 폴링), `POST /{session_id}/resume`, `GET /logs/{session_id}` |
| `backend/app/interfaces/api/staging.py` | `GET /{session_id}`, `POST .../approve|reject|commit`, `GET .../diff`, `PATCH .../nodes/{node_id}` |
| `backend/app/interfaces/api/graph.py` | `GET /topology`, `GET /concept/{name}/code` |

## C. 구현 순서 체크리스트

1. **`worker/tasks.py`** — 5단계 체인(Crawl→Extract→Write) + 상태 전이(`PENDING→CRAWLING→EXTRACTING→EXTRACTED→COMMITTED/FAILED`) + `pipeline_logs` 적재. 동시 승인/커밋은 `SELECT ... FOR UPDATE SKIP LOCKED`로 비차단 처리.
2. **`hybrid_resolver.py`** — `Score = JaroWinkler×0.4 + CosineName×0.3 + CosineDesc×0.3`, `MERGE_THRESHOLD=0.88` / `RELATED_THRESHOLD=0.72`. MERGE 확정 시 alias 풀 재임베딩 → PG `name_vector` Centroid Shifting.
3. **`neo4j_repo.py`** — 모든 노드/관계 `MERGE`(자연키), 리스트 필드는 `apoc.coll.toSet(...)`로 append+dedup, 동적 라벨은 `apoc.create.addLabels`. CodeExample은 `unq_id = f"{mechanism}_{lang}_{lang_version}_{framework}_{framework_version}"`로 버전별 분리.
4. **FastAPI 라우터** — `/api/pipeline/trigger`(`{doc_id}` → `session_id` 발급 + Celery 체인 시작), `/api/pipeline/stream/{session_id}`(SSE: `connected`/`log`/`step_update`/`heartbeat`/`finished`, `X-Accel-Buffering: no`), `/api/staging/{session_id}/{approve,reject,commit,diff}`, `PATCH .../nodes/{node_id}`.
5. **★ 보정점 반영** (신규 구현 시 처음부터 올바르게):
   - PostgreSQL 벡터 컬럼은 `vector(1024)`(BGE-M3 기준) — 768 아님.
   - `hybrid_resolver`가 계산한 `jaro`/`name_vec`/`desc_vec` 컴포넌트 점수를 `score_jaro_winkler`/`score_name_vector`/`score_desc_vector` 컬럼에 **실제로 저장**(원본 코드는 0.0 적재 버그 있음 — 역추적 가능하도록 수정).
   - 임베딩 클라이언트는 mock/production 분기 없이 단일 `BgeEmbeddingClient` 싱글톤으로 통일.
   - MERGE 액션에서도 4-Layer MERGE를 매번 재실행하지 말고, 라벨/배열(aliases/domains) 갱신만 분리해 불필요 비용 제거.

## D. 실행 프롬프트 골격 (새 세션에 그대로 붙여넣기)

```
아래 두 지침서를 읽고 5단계 Celery 파이프라인과 Graph Resolver를 구현해줘.

[outputs/idempotency.md 전문 붙여넣기]
---
[outputs/pipeline.md 전문 붙여넣기]

참고 소스 코드(로직/쿼리 패턴 포팅용, 함께 전달):
- domain/models.py, worker/tasks.py, infrastructure/graph/hybrid_resolver.py,
  infrastructure/graph/neo4j_service.py, adapters/db/neo4j_repo.py,
  infrastructure/llm/factory.py, interfaces/api/{documents,prescan,pipeline,staging,graph}.py

구현 순서:
1. worker/tasks.py — 5단계 체인(Crawl→Extract→Write), 상태 전이, SELECT FOR UPDATE SKIP LOCKED
2. hybrid_resolver.py — 3-Factor(0.4/0.3/0.3), MERGE≥0.88 / RELATED_TO≥0.72, Centroid Shifting
3. neo4j_repo.py — MERGE + apoc.coll.toSet + apoc.create.addLabels, CodeExample unq_id
4. FastAPI 라우터 — /pipeline/trigger, /pipeline/stream(SSE), /staging/{id}/approve|commit|diff
5. ★ 보정점: vector(1024), score_metrics 실제 저장, 임베딩 단일화, MERGE 중복 재적용 최소화

★ pipeline.md/idempotency.md 내 ★ 표시 항목은 신규 구현 시 처음부터 올바르게 반영해줘 (버그 재현 금지).
```

## 참고

- `outputs/prd.md`, `outputs/porting.md`, `outputs/cleanup-report.md`는 이 핸드오프(Phase B)에는 불필요 — 각각 범위 참조용(prd), 프론트엔드 이식(porting/Phase C), 이 프로젝트 정리용(cleanup-report)이다.
- 환경변수는 키만 전달: `DB_HOST/PORT/USER/PASSWORD/NAME`, `NEO4J_URI/USER/PASSWORD`, `CELERY_BROKER_URL/RESULT_BACKEND`, `EMBEDDING_MODEL`(기본 `BAAI/bge-m3`), `GEMINI_API_KEY/MODEL`, `USE_REAL_LLM`, `USE_REAL_EMBEDDING`, `APP_MODE`. 실제 값은 `.env`에서 직접 복사하지 말고 새 프로젝트의 시크릿 관리 방식에 맞게 채운다.
