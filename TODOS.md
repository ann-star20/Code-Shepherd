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

## Tag Node schema for domain membership (replaces multi-label + APOC)

**What**: Replace `:Concept:Security:Performance` multi-label approach with `(c:Concept)-[:TAGGED_WITH]->(t:Tag {name: "Security"})` relationships. Update all seed Cypher, Graph Writer specs, and T04 to use TAGGED_WITH instead of label assertions.

**Why**: APOC `apoc.create.addLabels()` is required for dynamic label assignment -- native Cypher `SET n:$labelName` is invalid. APOC is unavailable on Neo4j Aura Free tier. Tag Node achieves the same cross-domain filtering without plugins.

**How to apply**: Phase 1 -- update schema, seed Cypher, and Graph Writer specs before any code is written.
