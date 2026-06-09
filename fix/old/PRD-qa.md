## **10. QA 및 테스트 코드 명세 (Test Harness Specification)**

LangSmith 테스트 하네스 정책을 기반으로, 백엔드 프로젝트에서 반드시 격리 구현해야 하는 PyTest 테스트 코드의 구체적 범위와 Assert 명세를 정의한다. 레이스 컨디션·DB 락·LLM 비정형 출력을 완벽히 통제하기 위해 테스트는 4개 레이어로 분리 구축한다.

### **10.1. 테스트 하네스 격리 및 환경 선언 (conftest.py)**

실제 운영 DB 및 로컬 외부 도커를 건드려 데이터를 오염시키지 않도록, tests/harness/conftest.py에 PyTest 전용 격리 픽스처를 선언한다.

# tests/harness/conftest.py  (구조 명세)

@pytest.fixture(scope="function")  
def db_session():  
    """테스트 시작: schema.sql 주입 / 종료: ROLLBACK or TRUNCATE"""

@pytest.fixture(scope="function")  
def neo4j_session():  
    """테스트 시작: init_db.cypher 실행 / 종료: MATCH (n) DETACH DELETE n"""

@pytest.fixture(scope="session")  
def celery_app():  
    """CELERY_TASK_ALWAYS_EAGER=True — 비동기 태스크를 동기 실행으로 강제 전환  
    한 프로세스 내에서 디버깅 및 Assert 검증 가능"""

**픽스처 격리 원칙**:

* db_session: 테스트 함수 단위(scope="function") 롤백. 테스트 간 데이터 간섭 없음.  
* neo4j_session: 종료 시 MATCH (n) DETACH DELETE n 전체 정리. 고아 노드 잔류 방지.  
* celery_app: CELERY_TASK_ALWAYS_EAGER=True 설정으로 Celery 브로커 없이 동기 실행. 인프라 의존성 없는 순수 로직 검증.

### **10.2. 레이어 A — 결정론적 유틸 및 마스터 키 검증 (test_utils.py)**

LLM 통신 전 백엔드 단에서 수행되는 알고리즘의 무결성을 검증한다.

**T01. doc_id 발급 멱등성 테스트**

| 항목 | 내용 |
| :---- | :---- |
| 시나리오 | 동일한 URL과 동일한 본문 텍스트를 파라미터로 build_doc_id()를 3회 호출 |
| Assert | 반환된 doc_id 문자열이 3회 모두 완벽히 일치 |

def test_doc_id_idempotency():  
    url = "[https://docs.djangoproject.com/en/6.0/topics/security/](https://docs.djangoproject.com/en/6.0/topics/security/)"  
    content = "sample content"  
    ids = [build_doc_id("EXT", url, content) for _ in range(3)]  
    assert ids[0] == ids[1] == ids[2]

**T02. 동일 URL 내 콘텐츠 업데이트 변동 테스트**

| 항목 | 내용 |
| :---- | :---- |
| 시나리오 | URL은 https://noru-sh.tistory.com/25로 동일, 버전 1 텍스트와 버전 2 텍스트를 다르게 주입 |
| Assert | 두 doc_id 뒤쪽 8자리 해시가 서로 달라 독립 레코드로 격리됨을 검증 |

def test_doc_id_content_change():  
    url = "[https://noru-sh.tistory.com/25](https://noru-sh.tistory.com/25)"  
    id_v1 = build_doc_id("EXT", url, "version 1 content")  
    id_v2 = build_doc_id("EXT", url, "version 2 content — updated")  
    assert id_v1[-8:] != id_v2[-8:]      # 해시 8자리가 달라야 함  
    assert id_v1.split("_")[1] == id_v2.split("_")[1]  # URL 파트는 동일

### **10.3. 레이어 B — 데이터베이스 멱등성 및 제약 조건 검증 (test_db_migration.py)**

인프라 스크립트가 다중 환경(로컬/운영/하네스)에서 충돌 없이 자원을 구성하는지 검증한다.

**T03. PostgreSQL documents UPSERT 및 타임스탬프 트리거 테스트**

| 항목 | 내용 |
| :---- | :---- |
| 시나리오 | 동일 doc_id 레코드를 state='PENDING'으로 INSERT 후 state='CRAWLING'으로 ON CONFLICT DO UPDATE 수행 |
| Assert 1 | 중복 에러 없이 state가 'CRAWLING'으로 변경됨 |
| Assert 2 | updated_at이 created_at보다 미래 시간으로 자동 갱신됨 |

**T04. Neo4j 동적 다중 라벨 누적 및 MERGE 멱등성 테스트**

| 항목 | 내용 |
| :---- | :---- |
| 시나리오 | MemoryLeak 개념 노드 생성 Cypher를 2회 실행 후 apoc.create.addLabels로 ['Security', 'Performance'] 라벨을 동적 순차 부여 |
| Assert 1 | 전체 :Concept 노드 수 = 1 (Deduplication 보장) |
| Assert 2 | 대상 노드의 물리 라벨 배열을 추출했을 때 ['Concept', 'Security', 'Performance']가 누락 없이 집합으로 결합되어 존재함 |

def test_neo4j_multilabel_dynamic_deduplication(neo4j_session):  
    # Arrange — 2회 MERGE 및 동적 라벨 누적 실행 (멱등성 확인)  
    for _ in range(2):  
        neo4j_session.run("""  
            MERGE (c:Concept {name: 'MemoryLeak'})  
            WITH c  
            CALL apoc.create.addLabels(c, ['Security', 'Performance']) YIELD node  
            RETURN node  
        """)

    # Assert 1 — Concept 노드 중복 없음  
    cnt = neo4j_session.run(  
        "MATCH (c:Concept {name:'MemoryLeak'}) RETURN count(c) AS cnt"  
    ).single()["cnt"]  
    assert cnt == 1

    # Assert 2 — 물리 다중 라벨 결합 완벽성 검증  
    labels = neo4j_session.run("""  
        MATCH (c:Concept {name:'MemoryLeak'})  
        RETURN labels(c) AS labels  
    """).single()["labels"]  
    assert set(labels) == {"Concept", "Security", "Performance"}

### **10.4. 레이어 C — 비동기 파이프라인 및 스테이징 격리 검증 (test_pipeline_gate.py)**

"승인 게이트 전 운영 DB 쓰기 차단" 정책을 물리적으로 검증하는 핵심 레이어.

**T05. Extractor 완료 시점 운영 DB 격리 테스트**

| 항목 | 내용 |
| :---- | :---- |
| 시나리오 | Extractor Task가 성공적으로 구조화 JSON을 도출한 직후 DB 상태 스캔 |
| Assert 1 | concepts 테이블과 Neo4j Graph DB에 어떠한 데이터도 추가/변경되지 않음 |
| Assert 2 | staging_concepts 테이블에만 state='DRAFT' 레코드 1건 존재 |

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

**T06. 병렬 제출 레이스 컨디션 방어 테스트**

| 항목 | 내용 |
| :---- | :---- |
| 시나리오 | 동일 session_id·doc_id로 승인 요청을 Celery Worker 2개에 동시 투입 |
| Assert 1 | 먼저 진입한 Worker만 state='COMMITTED' 전환 성공 |
| Assert 2 | 늦게 온 Worker는 ObjectDeletedError 또는 커스텀 예외로 Fail-safe 처리됨 |

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

### **10.5. 레이어 D — LLM 품질 및 동적 확장 유효성 검증 (test_llm_eval.py)**

Gemini 출력 규격과 미등록 도메인 분류 처리망이 정상 작동하는지 검증한다.

**T07. Extractor 출력 JSON 배열 스키마 유효성 테스트**

| 항목 | 내용 |
| :---- | :---- |
| 시나리오 | Gemini가 반환한 Mock JSON을 Pydantic 모델 ConceptExtractionSchema로 파싱 |
| Assert 1 | ValidationError 없이 객체화 성공 |
| Assert 2 | domains 속성이 리스트(list[str]) 타입이며, 개수가 1개 이상 존재함을 검증 |

def test_extractor_array_schema_validation():  
    mock_output = {  
        "concept_name": "MemoryLeak",  
        "domains": ["security", "performance"], # 배열 형태 검증  
        "concept_type": "vulnerability_root_cause",  
        "cwe_id": "CWE-401",  
        "severity": "high",  
        "description_ko": "메모리 누수 결함",  
        "aliases": ["Memory Leak", "메모리 누수"],  
    }  
    schema = ConceptExtractionSchema(**mock_output)  
    assert isinstance(schema.domains, list)

**T08. 미등록 도메인 유입 시 DOMAIN_PENDING 상태 전이 테스트**

| 항목 | 내용 |
| :---- | :---- |
| 시나리오 | domain_registry에 없는 ["compliance"] 도메인을 포함한 데이터 파이프라인 가동 |
| Assert 1 | 시스템 에러로 다운되지 않고 staging_concepts 레코드에 성공적으로 포획됨 |
| Assert 2 | 적재된 레코드의 state 값이 명확하게 'DOMAIN_PENDING' 마킹됨을 검증 |

### **13. 프로젝트 완료 조건 (Definition of Done)**

#### **13.1. 기능적 완료 조건**

| 번호 | 조건 | 판정 방법 |
| :---- | :---- | :---- |
| F-01 | 1~5개 URL 입력 → 파이프라인 완전 실행 → Neo4j Concept 동적 다중 라벨 생성까지 End-to-End 동작 | 실제 Django Docs URL 투입 후 토폴로지 뷰 확인 |
| F-02 | Human-in-the-Loop: 메타데이터 자동 추론 성공률 ≥ 80% (Django·Spring·FastAPI URL 기준) | Pre-scan 20건 테스트 결과 |
| F-03 | 최종 승인 게이트: DRAFT / DOMAIN_PENDING → APPROVED → COMMITTED 상태 전이 정상 작동 | T05·T06·T08 하네스 통과 확인 |
| F-04 | 프론트엔드 가상 노드 미리보기: DRAFT 노드 점선 및 미등록 도메인 배지 렌더링 정상 동작 | Chrome 브라우저 스모크 테스트 |
| F-05 | 성능 도메인 4종 안티패턴 및 보안 도메인 AWASP 시드 데이터 무결성 멱등 적재 | verify_seed.py 실행 결과 0 오류 |

#### **13.2. 비기능적 성능 및 품질 지표**

| 번호 | 지표 | 목표값 |
| :---- | :---- | :---- |
| Q-01 | LangSmith Pre-Eval 스키마 이탈률 | **0%** |
| Q-02 | pytest tests/ 전체 통과율 | **8 / 8 PASSED** |
| Q-03 | 테스트 커버리지 | **≥ 85%** |
| Q-04 | 단일 URL End-to-End 처리 시간 (크롤링 + LLM 추출 + DB 적재) | **≤ 60초** |
| Q-05 | 동일 URL 재처리 시 LLM 재호출 없이 캐시 응답 처리 | 토큰 소모 **0** |
| Q-06 | 프로덕션 HITL 수정률 (초기 배포 2주 기준) | **< 20%** |

#### **13.3. 산출물 완료 조건**

| 번호 | 산출물 | 위치 |
| :---- | :---- | :---- |
| A-01 | PRD 최신 버전 (v2 4레이어 아키텍처) | docs/PRD-domain.md |
| A-02 | docker-compose.yml + .env.local + .env.prod | infra/ |
| A-03 | 시드 스크립트 및 JSON 에셋 (schema.sql, seed_postgres.py 등) | scripts/seed/ |
| A-04 | LangSmith 평가 데이터셋 (extractor_schema_eval/) | langsmith_datasets/ |
| A-05 | 테스트 하네스 4개 파일 (test_utils.py ~ test_llm_eval.py) | tests/harness/ |
| A-06 | verify_seed.py 정합성 검증 스크립트 | scripts/seed/ |

