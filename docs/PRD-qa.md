
## 10. QA 및 테스트 코드 명세 (Test Harness Specification)

LangSmith 테스트 하네스 정책을 기반으로, 백엔드 프로젝트에서 반드시 격리 구현해야 하는 PyTest 테스트 코드의 구체적 범위와 Assert 명세를 정의한다. 레이스 컨디션·DB 락·LLM 비정형 출력을 완벽히 통제하기 위해 테스트는 4개 레이어로 분리 구축한다.

### 10.1. 테스트 하네스 격리 및 환경 선언 (conftest.py)

실제 운영 DB 및 로컬 외부 도커를 건드려 데이터를 오염시키지 않도록, `tests/harness/conftest.py`에 PyTest 전용 격리 픽스처를 선언한다.

```python
# tests/harness/conftest.py  (구조 명세)

@pytest.fixture(scope="function")
def db_session():
    """테스트 시작: schema.sql + seed_data.sql 주입 / 종료: ROLLBACK or TRUNCATE"""

@pytest.fixture(scope="function")
def neo4j_session():
    """테스트 시작: seed_data.cypher 실행 / 종료: MATCH (n) DETACH DELETE n"""

@pytest.fixture(scope="session")
def celery_app():
    """CELERY_TASK_ALWAYS_EAGER=True — 비동기 태스크를 동기 실행으로 강제 전환
    한 프로세스 내에서 디버깅 및 Assert 검증 가능"""
```

**픽스처 격리 원칙**:
- `db_session`: 테스트 함수 단위(`scope="function"`) 롤백. 테스트 간 데이터 간섭 없음.
- `neo4j_session`: 종료 시 `MATCH (n) DETACH DELETE n` 전체 정리. 고아 노드 잔류 방지.
- `celery_app`: `CELERY_TASK_ALWAYS_EAGER=True` 설정으로 Celery 브로커 없이 동기 실행. 인프라 의존성 없는 순수 로직 검증.

### 10.2. 레이어 A — 결정론적 유틸 및 마스터 키 검증 (`test_utils.py`)

LLM 통신 전 백엔드 단에서 수행되는 알고리즘의 무결성을 검증한다.

**T01. `doc_id` 발급 멱등성 테스트**

| 항목 | 내용 |
|------|------|
| 시나리오 | 동일한 URL과 동일한 본문 텍스트를 파라미터로 `build_doc_id()`를 3회 호출 |
| Assert | 반환된 `doc_id` 문자열이 3회 모두 완벽히 일치 |

```python
def test_doc_id_idempotency():
    url = "https://docs.djangoproject.com/en/6.0/topics/security/"
    content = "sample content"
    ids = [build_doc_id("EXT", url, content) for _ in range(3)]
    assert ids[0] == ids[1] == ids[2]
```

**T02. 동일 URL 내 콘텐츠 업데이트 변동 테스트**

| 항목 | 내용 |
|------|------|
| 시나리오 | URL은 `https://noru-sh.tistory.com/25`로 동일, 버전 1 텍스트와 버전 2 텍스트를 다르게 주입 |
| Assert | 두 `doc_id` 뒤쪽 8자리 해시가 서로 달라 독립 레코드로 격리됨을 검증 |

```python
def test_doc_id_content_change():
    url = "https://noru-sh.tistory.com/25"
    id_v1 = build_doc_id("EXT", url, "version 1 content")
    id_v2 = build_doc_id("EXT", url, "version 2 content — updated")
    assert id_v1[-8:] != id_v2[-8:]      # 해시 8자리가 달라야 함
    assert id_v1.split("_")[1] == id_v2.split("_")[1]  # URL 파트는 동일
```

### 10.3. 레이어 B — 데이터베이스 멱등성 및 제약 조건 검증 (`test_db_migration.py`)

인프라 스크립트가 다중 환경(로컬/운영/하네스)에서 충돌 없이 자원을 구성하는지 검증한다.

**T03. PostgreSQL `documents` UPSERT 및 타임스탬프 트리거 테스트**

| 항목 | 내용 |
|------|------|
| 시나리오 | 동일 `doc_id` 레코드를 `state='PENDING'`으로 INSERT 후 `state='CRAWLING'`으로 `ON CONFLICT DO UPDATE` 수행 |
| Assert 1 | 중복 에러 없이 `state`가 `'CRAWLING'`으로 변경됨 |
| Assert 2 | `updated_at`이 `created_at`보다 미래 시간으로 자동 갱신됨 |

**T04. Neo4j Tag Node 방식 도메인 태깅 + MERGE 멱등성 테스트**

| 항목 | 내용 |
|------|------|
| 시나리오 | `MemoryLeak` 개념 노드 생성 Cypher를 2회 실행 후 Tag Node(`Security`, `Performance`) 관계를 순차 부여 |
| Assert 1 | 전체 `:Concept` 노드 수 = 1 (Deduplication 보장) |
| Assert 2 | `(MemoryLeak)-[:TAGGED_WITH]->(Security)` 및 `(MemoryLeak)-[:TAGGED_WITH]->(Performance)` 관계 각 1개씩만 존재 |

```python
def test_neo4j_tag_node_deduplication(neo4j_session):
    # Arrange — 2회 MERGE 실행 (멱등성 확인)
    for _ in range(2):
        neo4j_session.run("""
            MERGE (c:Concept {name: 'MemoryLeak'})
            WITH c
            UNWIND ['Security', 'Performance'] AS tag_name
              MERGE (t:Tag {name: tag_name})
              MERGE (c)-[:TAGGED_WITH]->(t)
        """)

    # Assert 1 — Concept 노드 중복 없음
    cnt = neo4j_session.run(
        "MATCH (c:Concept {name:'MemoryLeak'}) RETURN count(c) AS cnt"
    ).single()["cnt"]
    assert cnt == 1

    # Assert 2 — Tag 관계 중복 없음 (각 1개)
    tags = neo4j_session.run("""
        MATCH (c:Concept {name:'MemoryLeak'})-[:TAGGED_WITH]->(t:Tag)
        RETURN collect(t.name) AS tags
    """).single()["tags"]
    assert set(tags) == {"Security", "Performance"}
```

### 10.4. 레이어 C — 비동기 파이프라인 및 스테이징 격리 검증 (`test_pipeline_gate.py`)

"승인 게이트 전 운영 DB 쓰기 차단" 정책을 물리적으로 검증하는 핵심 레이어.

**T05. Extractor 완료 시점 운영 DB 격리 테스트**

| 항목 | 내용 |
|------|------|
| 시나리오 | Extractor Task가 성공적으로 구조화 JSON을 도출한 직후 DB 상태 스캔 |
| Assert 1 | `concepts` 테이블과 Neo4j Graph DB에 어떠한 데이터도 추가/변경되지 않음 |
| Assert 2 | `staging_concepts` 테이블에만 `state='DRAFT'` 레코드 1건 존재 |

```python
def test_extractor_does_not_touch_master_db(db_session, neo4j_session, celery_app):
    run_extractor_task(doc_id="EXT_test_abc12345")  # ALWAYS_EAGER로 동기 실행

    master_count = db_session.execute("SELECT COUNT(*) FROM concepts").scalar()
    assert master_count == 0                         # 운영 테이블 미접촉

    neo4j_count = neo4j_session.run(
        "MATCH (c:Concept) RETURN count(c) AS cnt"
    ).single()["cnt"]
    assert neo4j_count == 0                          # 그래프 미접촉

    draft_count = db_session.execute(
        "SELECT COUNT(*) FROM staging_concepts WHERE state='DRAFT'"
    ).scalar()
    assert draft_count == 1                          # 스테이징에만 존재
```

**T06. 병렬 제출 레이스 컨디션 방어 테스트**

| 항목 | 내용 |
|------|------|
| 시나리오 | 동일 `session_id`·`doc_id`로 승인 요청을 Celery Worker 2개에 동시 투입 |
| Assert 1 | 먼저 진입한 Worker만 `state='COMMITTED'` 전환 성공 |
| Assert 2 | 늦게 온 Worker는 `ObjectDeletedError` 또는 커스텀 예외로 Fail-safe 처리됨 |

```python
def test_parallel_approve_race_condition(db_session, celery_app):
    session_id = "test-session-001"
    create_draft_staging(session_id=session_id)  # DRAFT 레코드 사전 생성

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(call_approve_api, session_id),
            executor.submit(call_approve_api, session_id),
        ]
        results = [f.result() for f in futures]

    committed = db_session.execute(
        "SELECT COUNT(*) FROM staging_concepts WHERE state='COMMITTED'"
    ).scalar()
    assert committed == 1                            # 단 1건만 COMMITTED

    statuses = [r["status"] for r in results]
    assert statuses.count("success") == 1
    assert statuses.count("conflict") == 1           # 나머지는 예외 처리
```

### 10.5. 레이어 D — LLM 품질 및 LangSmith 연동 검증 (`test_llm_eval.py`)

Gemini 출력 규격과 LangSmith 피드백 추적망이 정상 작동하는지 검증한다.

**T07. Extractor 출력 JSON 스키마 유효성 테스트**

| 항목 | 내용 |
|------|------|
| 시나리오 | Gemini가 반환한 Mock JSON을 Pydantic 모델 `ConceptExtractionSchema`로 파싱 |
| Assert 1 | `ValidationError` 없이 객체화 성공 |
| Assert 2 | `concept_domain` 값이 `['security', 'performance', 'both']` 범위 내에 존재 |

```python
def test_extractor_schema_validation():
    mock_output = {
        "concept_name": "XSS",
        "concept_domain": "security",
        "concept_type": "vulnerability_root_cause",
        "cwe_id": "CWE-79",
        "severity": "HIGH",
        "description_ko": "크로스 사이트 스크립팅 취약점",
        "aliases": ["Cross-Site Scripting", "크로스 사이트 스크립팅"],
    }
    schema = ConceptExtractionSchema(**mock_output)   # ValidationError 없어야 함
    assert schema.concept_domain in {"security", "performance", "both"}
```

**T08. LangSmith 피드백 루프 API 트리거 테스트**

| 항목 | 내용 |
|------|------|
| 시나리오 | HITL 수정 가상 API 호출 시 `langsmith.Client().create_feedback()` 정상 호출 여부 Mocking 검증 |
| Assert | 페이로드에 `score=0`, `run_id`, 수정 전/후 diff 메시지가 누락 없이 매핑됨 |

```python
def test_langsmith_feedback_trigger():
    with patch("langsmith.Client.create_feedback") as mock_feedback:
        call_hitl_correction_api(
            run_id="run-abc-123",
            before_json={"concept_domain": "security"},
            after_json={"concept_domain": "both"},
        )
        mock_feedback.assert_called_once()
        kwargs = mock_feedback.call_args.kwargs
        assert kwargs["score"] == 0
        assert kwargs["run_id"] == "run-abc-123"
        assert "before" in kwargs["comment"] and "after" in kwargs["comment"]
```

### 10.6. QA 완료 판단 기준 (Definition of Done — QA)

`pytest tests/`를 실행했을 때 아래 조건을 모두 충족해야 QA 통과로 판정한다.

```
tests/harness/test_utils.py          PASSED [ 25%]   # T01, T02
tests/harness/test_db_migration.py   PASSED [ 50%]   # T03, T04
tests/harness/test_pipeline_gate.py  PASSED [ 75%]   # T05, T06
tests/harness/test_llm_eval.py       PASSED [100%]   # T07, T08

==================== 8 passed in 2.34s ====================
```

| 판정 기준 | 목표값 |
|-----------|--------|
| 전체 테스트 통과율 | 8 / 8 PASSED |
| 테스트 커버리지 | ≥ 85% |
| DB 잔류 레코드 | 테스트 종료 후 마스터 테이블 및 그래프 고아 노드 0건 |
| 실행 시간 | ≤ 30초 (하네스 컨테이너 기준) |

---

## 13. 프로젝트 완료 조건 (Definition of Done)

각 Phase별 개발 완료 판정 및 최종 릴리즈 승인은 아래의 정량적·정성적 기준을 모두 충족할 때에만 승인된다.

### 13.1. 기능적 완료 조건

| 번호 | 조건 | 판정 방법 |
|------|------|-----------|
| F-01 | 1~5개 URL 입력 → 파이프라인 완전 실행 → Neo4j Concept 노드 생성까지 End-to-End 동작 | 실제 Django Docs URL 투입 후 토폴로지 뷰 확인 |
| F-02 | Human-in-the-Loop: 메타데이터 자동 추론 성공률 ≥ 80% (Django·Spring·FastAPI URL 기준) | Pre-scan 20건 테스트 결과 |
| F-03 | 최종 승인 게이트: DRAFT→APPROVED→COMMITTED 상태 전이 및 4대 커밋 규칙 모두 동작 | T05·T06 하네스 통과 확인 |
| F-04 | 프론트엔드 가상 노드 미리보기: DRAFT 노드 점선 렌더링 및 승인 후 실선 전환 정상 동작 | Chrome 브라우저 스모크 테스트 |
| F-05 | 성능 도메인 4종 안티패턴(N+1Query 등) 및 보안 도메인 OWASP 시드 데이터 정상 적재 | `verify_seed.py` 실행 결과 0 오류 |

### 13.2. 비기능적 성능 및 품질 지표

| 번호 | 지표 | 목표값 |
|------|------|--------|
| Q-01 | LangSmith Pre-Eval 스키마 이탈률 | **0%** |
| Q-02 | `pytest tests/` 전체 통과율 | **8 / 8 PASSED** |
| Q-03 | 테스트 커버리지 | **≥ 85%** |
| Q-04 | 단일 URL End-to-End 처리 시간 (크롤링 + LLM 추출 + DB 적재) | **≤ 60초** |
| Q-05 | 동일 URL 재처리 시 LLM 재호출 없이 캐시 응답 처리 | 토큰 소모 **0** |
| Q-06 | 프로덕션 HITL 수정률 (초기 배포 2주 기준) | **< 20%** |

### 13.3. 산출물 완료 조건

| 번호 | 산출물 | 위치 |
|------|--------|------|
| A-01 | PRD 최신 버전 (v0.9+) | `docs/PRD_Knowledge_Graph_Agent.md` |
| A-02 | `docker-compose.yml` + `.env.local` + `.env.prod` | `infra/` |
| A-03 | 시드 스크립트 (`schema.sql`, `seed_data.sql`, `seed_data.cypher`) | `scripts/seed/` |
| A-04 | LangSmith 평가 데이터셋 (`extractor_schema_eval/`) | `langsmith_datasets/` |
| A-05 | 테스트 하네스 4개 파일 (`test_utils.py` ~ `test_llm_eval.py`) | `tests/harness/` |
| A-06 | `verify_seed.py` 정합성 검증 스크립트 | `scripts/seed/` |

---

