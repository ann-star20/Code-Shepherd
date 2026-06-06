# Phase 1 원자 단위 분할 — Spec → Test → Impl
## 0. 코딩 전 문서 수정 (테스트 없음)
ID	작업	파일	예상 시간
<!-- D0-1	PRD §14.2 다이어그램에서 Celery 제거	docs/PRD_Knowledge_Graph_Agent.md	20min -->
D0-2	PRD §11 COMMITTED_PENDING_RESOLVE 상태 제거	동상	20min

## A. 도메인 모델 (순수 Python, 인프라 의존 없음)

`A1-Spec   ConceptExtractionSchema (Pydantic), build_doc_id() 시그니처, PipelineState Enum
A1-Test   T01 doc_id 멱등성 / T02 rsplit 수정 버전 / T07 스키마 유효성
A1-Impl   domain/models.py  domain/pipeline.py`

AAA 예시 (T02):


`# Arrange
url = "https://docs.example.com/en/some_topic/security/"
# Act
id_v1 = build_doc_id("EXT", url, "content v1")
id_v2 = build_doc_id("EXT", url, "content v2")
# Assert — rsplit로 해시만 분리
assert id_v1.rsplit("_", 1)[0] == id_v2.rsplit("_", 1)[0]
assert id_v1.rsplit("_", 1)[1] != id_v2.rsplit("_", 1)[1]`

## B. LLM DIP + MockClient

`B1-Spec   ILLMClient ABC, _parse_json_safely 3가지 에러 케이스 명세
            (1) 잘못된 JSON  (2) 마크다운 래핑 (```json...```)  (3) Pydantic 스키마 위반
          → 모두 pipeline_jobs.status = 'FAILED', error_message 저장
B1-Test   T09-T11 DIP 컴플라이언스 / T12 malformed JSON → FAILED 상태
B1-Impl   infrastructure/llm/interface.py  mock_client.py  gemini_client.py  factory.py`
AAA 예시 (T12):


`# Arrange
mock_bad_client = BadJsonMockClient()   # "not json" 반환
task = RunPipelineUsecase(llm_client=mock_bad_client, ...)
# Act
await task.execute(doc_id="EXT_test_abc12345", ...)
# Assert
job = await db.get_pipeline_job("EXT_test_abc12345")
assert job.status == "FAILED"
assert "parse error" in job.error_message`
## C. DB 스키마 + Tag Node 시드

`C1-Spec   PostgreSQL DDL (documents, staging_concepts, concepts, pipeline_jobs)
          Neo4j Tag Node Cypher: (c:Concept)-[:TAGGED_WITH]->(t:Tag {name:"Security"})
          OWASP 2025 JSON 파일 (A01:2025 ~ A10:2025)
C1-Test   T03 PostgreSQL UPSERT + updated_at 트리거
          T04 Tag Node MERGE 멱등성
C1-Impl   scripts/seed/security/*.json *.sql *.cypher
          infrastructure/database/migrations/`
AAA 예시 (T04):


`# Arrange
neo4j_session.run("MERGE (c:Concept {name: 'MemoryLeak'})")
# Act — Tag Node 방식
neo4j_session.run("""
    MATCH (c:Concept {name: 'MemoryLeak'})
    MERGE (t:Tag {name: 'security'})
    MERGE (c)-[:TAGGED_WITH]->(t)
""")
# Assert
result = neo4j_session.run("""
    MATCH (c:Concept {name:'MemoryLeak'})-[:TAGGED_WITH]->(t:Tag)
    RETURN collect(t.name) AS tags
""").single()
assert "security" in result["tags"]`
## D. 파이프라인 코어

`D1-Spec   PipelineTask 프로토콜 (execute/cancel)
          run_pipeline.py: asyncio.gather(return_exceptions=True) + Semaphore(GEMINI_RPM_LIMIT)
          main.py 시작 시 RUNNING 고아 잡 → FAILED 전환 (10분 초과)
D1-Test   T05 staging 격리 (run_sync_pipeline_task 픽스처, celery_app 제거)
          T13 startup reconciliation
D1-Impl   usecases/run_pipeline.py  main.py (startup event)
          config/settings.py (GEMINI_RPM_LIMIT 환경변수 추가)`
## E. 승인 게이트

`E1-Spec   approve_staging.py: SELECT FOR UPDATE SKIP LOCKED
          세션 모델: 1 pipeline trigger = 1 session_id (D16 결정)
          API: POST /api/staging/{session_id}/approve
E1-Test   T06 레이스 컨디션 재설계
            asyncio.gather(approve(sid), approve(sid))
            → 1 success + 1 StagingConflictError
          T08 LangSmith 피드백 트리거
E1-Impl   usecases/approve_staging.py  interfaces/api/staging.py`
## F. CI/CD

`F1-Spec   .github/workflows/ci.yml 구조:
            on: [push, pull_request]
            jobs: lint(ruff/black) → test(pytest + DB 픽스처 컨테이너) → docker-build
F1-Impl   .github/workflows/ci.yml`
# 실행 순서 (의존성 기준)

D0 (문서)
  ↓
A (도메인 모델) ←── B (LLM DIP) ← Lane A/B 병렬
  ↓
C (DB 스키마 + 시드)
  ↓
D (파이프라인 코어)
  ↓
E (승인 게이트)
  ↓
F (CI/CD)