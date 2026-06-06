# TODOS

## T06 race condition test redesign

**What**: Redesign T06 (parallel approve race condition) to use `asyncio.gather()` + PostgreSQL `SELECT FOR UPDATE SKIP LOCKED` instead of `ThreadPoolExecutor` + Celery workers.

**Why**: Celery was removed from v1 (design doc D2). The original T06 used Celery worker isolation to model true process-level concurrency. FastAPI BackgroundTasks run in the same event loop, so `ThreadPoolExecutor` doesn't reproduce the same failure mode. Using `asyncio.gather()` against the `approve_staging` usecase directly, with `SELECT FOR UPDATE SKIP LOCKED` as the DB-level single-winner enforcer, correctly models the async concurrent approval scenario.

**How to apply**: Phase 1 -- when writing `usecases/approve_staging.py`, ensure the staging row SELECT uses `FOR UPDATE SKIP LOCKED`. T06 test calls `asyncio.gather(approve_staging(session_id), approve_staging(session_id))` and asserts exactly one succeeds and one raises `StagingConflictError`.

**Depends on**: `usecases/approve_staging.py` usecase + PostgreSQL `SELECT FOR UPDATE SKIP LOCKED` pattern.

---

## CI/CD GitHub Actions workflow YAML

**What**: Define `.github/workflows/ci.yml` with lint (ruff/black), pytest (backend, with DB fixture containers), LangSmith pre-eval gate, Docker build+push on merge to main.

**Why**: The design doc mentions CI/CD via GitHub Actions but no workflow file is specified anywhere in the PRD. Code without CI is not open-source-ready.

**How to apply**: Phase 1 milestone -- create the YAML alongside the first backend commit so CI runs from day 1.

---

## Frontend test coverage (Vitest)

**What**: Add Vitest unit tests for `useGraphMerge.ts`, `useStagingApproval.ts`, `usePipelineSSE.ts`.

**Why**: No frontend tests are specified in the PRD. `useGraphMerge` contains the virtual node merge logic -- a bug here produces incorrect topology display. PRD section 14.4 specifies the expected AAA behavior in pseudocode, so test cases are partially written already.

**How to apply**: Phase 3 -- write Vitest tests alongside the hook implementations.

---

## PRD section 14.2 architecture diagram update

**What**: Update the component communication diagram to replace the Celery/Redis flow with FastAPI BackgroundTasks + PipelineTask protocol.

**Why**: The diagram shows `task.delay()` to Celery Worker to Redis to SSE. Celery was removed. The diagram misleads every engineer who reads section 14.

**How to apply**: Before Phase 1 coding begins. One-time PRD doc update.

---

## PRD section 11 -- Remove COMMITTED_PENDING_RESOLVE state from v1

**What**: Remove `COMMITTED_PENDING_RESOLVE` from the v1 state machine. Change `APPROVED -> COMMITTED_PENDING_RESOLVE -> COMMITTED` to `APPROVED -> COMMITTED`. Move Rule 3 (Link Resolver trigger) to a v2 appendix.

**Why**: Link Resolver is deferred to v2 (D5). PRD section 11 Rule 3 defines it as a blocking synchronous step in the commit path. These contradict each other.

**How to apply**: Before Phase 2 (Graph Writer implementation). Update section 11 + state diagram in section 15.

---

## [Core] APOC 플러그인 기반 동적 다중 라벨(Multi-label) 아키텍처 고수

**What**: 임시 우회책이었던 `(c:Concept)-[:TAGGED_WITH]->(t:Tag)` 관계형 구조를 전면 폐기함. 원래 설계대로 단일 `Concept` 허브 노드에 물리적 다중 라벨(예: `:Concept:security:Performance`)을 누적하는 방식을 최종 확정함. 모든 초기 시드 Cypher, Graph Writer 스펙, 그리고 `T04` 테스트 코드를 APOC 동적 라벨 추가 구문으로 동기화함.

**Why**: 
1. 로컬 및 자체 호스팅 환경(Neo4j Community 에디션)에서 APOC 플러그인이 완벽히 지원되므로, Cypher의 변수 라벨링 한계를 `apoc.create.addLabels()` 프로시저로 우아하게 해결할 수 있음.
2. 유령 `Tag` 노드를 양산할 경우 발생하는 슈퍼노드(Supernode) 병목과 관계선 폭발 현상을 원천 차단하고, 그래프 데이터 모델의 진실성(정합성)을 지키기 위함.
3. `MATCH (c:Concept:security)`와 같이 Neo4j 네이티브 하드웨어 인덱스 가속을 100% 활용한 초고속 필터링 조회가 가능함.

**How to apply (Phase 1 가동 지침)**:
1. `scripts/seed/` 내의 온톨로지 적재 쿼리를 단일 `MERGE (c:Concept {name: $name})` 후 `CALL apoc.create.addLabels(c, $domain_labels)`를 호출하는 구조로 원자화할 것.
2. `backend/tests/harness/test_db_migration.py (T04)` 테스트 자산의 Assert 구문을 `labels(c)` 함수를 사용하여 물리 라벨 세트가 누적 단조 증가하는지 검증하도록 수정할 것.