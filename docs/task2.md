<!-- # Phase 2 — Agent Pipeline 작업 계획

> 방법론: **SDD(Spec → 인터페이스 설계) → TDD(AAA 테스트 먼저) → 구현** 순서 엄수  
> 브랜치: `feat/k-graph-agent`  
> 기존 인프라: PostgreSQL:5433 · Neo4j:bolt://127.0.0.1:7687  
> 기존 코드: ILLMClient DIP · PipelineTask Protocol · approve_staging(SKIP LOCKED)

---

## 진행 현황

- [ ] G1: FastAPI main.py — lifespan asyncpg pool + 라우터 등록
- [x] G2: HttpCrawler — 비동기 URL fetch + 텍스트 청크 분할
- [ ] G3: Pre-scan Layer — URL 패턴 + HTML 메타 추론
- [ ] G4: ConceptExtractionSchema + extract_concepts usecase
- [ ] G5: write_staging_draft — staging_concepts DRAFT 적재
- [ ] G6: PipelineTaskImpl — Crawler→Extractor→Draft 단일 파이프라인
- [ ] G7: Staging Gate API 완성 — /reject + /diff + GET 목록
- [ ] G8: GraphWriter — MERGE Concept + TAGGED_WITH (Tag Node)
- [ ] G9: commit_staging — APPROVED → concepts + Neo4j → COMMITTED
- [ ] G10: LinkResolver — aliases SAME_AS 후보 탐색

---

## G1: FastAPI main.py

### SDD

**파일**: `backend/app/main.py`  
**역할**: FastAPI 앱 엔트리포인트. lifespan으로 asyncpg pool 생성·해제. staging 라우터 마운트.

```
lifespan:
  startup  → pool = await asyncpg.create_pool(DB_DSN), app.state.pool = pool
  shutdown → await pool.close()

_get_conn (staging.py) → conn = await request.app.state.pool.acquire()
GET /health → {"status": "ok"}
```

**수정 대상**: `backend/app/interfaces/api/staging.py` — `_get_conn` placeholder 교체

### TDD (AAA)

파일: `backend/tests/harness/test_main.py`

| ID | Arrange | Act | Assert |
|----|---------|-----|--------|
| T_main_health | `TestClient(app)` | `GET /health` | 200, `{"status":"ok"}` |
| T_main_pool_wired | TestClient + lifespan | `app.state.pool` | not None |

---

## G2: HttpCrawler

### SDD

**파일**: `backend/app/infrastructure/crawler/http_crawler.py`

```python
@dataclass
class CrawlResult:
    url: str
    content: str       # BeautifulSoup 정제 텍스트 (script/style 제거)
    etag: str | None
    status_code: int

async def fetch(url: str, session: aiohttp.ClientSession) -> CrawlResult: ...

def chunk(content: str, max_chars: int = 3000) -> list[str]:
    # 단락(\n\n) 기준 분할. 마지막 청크 < 500자이면 앞 청크에 병합
```

**의존**: `aiohttp`, `beautifulsoup4`

### TDD (AAA)

파일: `backend/tests/harness/test_crawler.py`

| ID | Arrange | Act | Assert |
|----|---------|-----|--------|
| T_crawl_returns_text | aiohttp mock → 200 + HTML with `<p>Hello</p>` | `fetch(url, session)` | `"Hello" in result.content` |
| T_crawl_strips_script | HTML with `<script>alert(1)</script>` | `fetch(url, session)` | `"alert" not in result.content` |
| T_crawl_captures_etag | response header `ETag: "abc123"` | `fetch(url, session)` | `result.etag == "abc123"` |
| T_chunk_splits | content 10000자 | `chunk(content, 3000)` | `len(chunks) >= 3` and all `<= 3500자` |
| T_chunk_merges_short_tail | 마지막 단락 200자 | `chunk(content, 3000)` | 마지막 chunk `>= 500자` |

---

## G3: Pre-scan Layer

### SDD

**파일**: `backend/app/usecases/prescan.py`

```python
@dataclass
class PreScanResult:
    framework: str | None
    version: str | None
    lang: str | None      # "EN" | "KO" | None
    confidence: float     # 0.0 ~ 1.0

def prescan_url(url: str) -> PreScanResult: ...
    # URL 경로에서 framework/version 키워드 매칭
    # docs.djangoproject.com/en/6.0/ → Django 6.0 EN, confidence=0.9

def prescan_html(html: str) -> PreScanResult: ...
    # <title>, <h1>, <html lang> 파싱

def prescan(url: str, html: str) -> PreScanResult: ...
    # prescan_url + prescan_html 결합, confidence 합산
```

### TDD (AAA)

파일: `backend/tests/harness/test_prescan.py`

| ID | Arrange | Act | Assert |
|----|---------|-----|--------|
| T_prescan_django_url | `url="https://docs.djangoproject.com/en/6.0/topics/security/"` | `prescan_url(url)` | `framework=="Django"`, `version=="6.0"`, `lang=="EN"` |
| T_prescan_html_title | `html="<title>Spring Security 6.1 Reference</title>"` | `prescan_html(html)` | `framework=="Spring"` |
| T_prescan_html_lang | `html='<html lang="ko">'` | `prescan_html(html)` | `lang=="KO"` |
| T_prescan_unknown_low | random URL + empty HTML | `prescan(url, html)` | `confidence < 0.3` |

---

## G4: ConceptExtractionSchema + extract_concepts

### SDD

**파일**: `backend/app/interfaces/schemas/concept_extraction.py`

```python
class ConceptExtractionSchema(BaseModel):
    concept_name: str
    concept_domain: Literal["security", "performance", "both"]
    concept_type: str
    cwe_id: str | None = None
    owasp_category: str | None = None
    severity: Literal["critical","high","medium","low"] | None = None
    security_mechanisms: list[str] = []
    affected_components: list[str] = []
    config_properties: list[dict] = []
    root_cause: str = ""
    description_ko: str
    aliases: list[str] = []
```

**파일**: `backend/app/usecases/extract_concepts.py`

```python
async def extract_concepts(
    doc_id: str,
    chunks: list[str],
    llm: ILLMClient,
) -> list[ConceptExtractionSchema]:
    # 청크별 LLM 호출 → JSON 파싱 → Pydantic 검증
    # 동일 concept_name 중복 제거 (첫 번째 유지)
```

### TDD (AAA)

파일: `backend/tests/harness/test_extractor.py`

| ID | Arrange | Act | Assert |
|----|---------|-----|--------|
| T_extract_schema_valid | MockLLMClient → XSS 유효 JSON | `extract_concepts(doc_id, chunks, mock)` | `result[0]` is `ConceptExtractionSchema` |
| T_extract_dedup | MockLLMClient → concept_name="XSS" 2청크 반환 | `extract_concepts(...)` | `len(result) == 1` |
| T_extract_domain_both | mock → `concept_domain="both"` | `extract_concepts(...)` | `result[0].concept_domain == "both"` |
| T_extract_invalid_filtered | mock → severity="UNKNOWN" | `extract_concepts(...)` | ValidationError 발생 또는 해당 항목 제외 |

---

## G5: write_staging_draft

### SDD

**파일**: `backend/app/usecases/write_staging_draft.py`

```python
async def write_staging_draft(
    session_id: str,
    doc_id: str,
    concepts: list[ConceptExtractionSchema],
    conn: asyncpg.Connection,
) -> int:
    # staging_concepts에 DRAFT 행 INSERT
    # concept_json = concept.model_dump() → JSONB
    # 반환: 삽입된 행 수
```

### TDD (AAA)

파일: `backend/tests/harness/test_write_staging.py`

| ID | Arrange | Act | Assert |
|----|---------|-----|--------|
| T_write_draft_inserts | asyncpg_pool + 2개 ConceptSchema | `write_staging_draft(sid, doc_id, concepts, conn)` | DB에 2행, `status='DRAFT'` |
| T_write_draft_json | concept with `description_ko="테스트"` | `write_staging_draft(...)` | `concept_json->>'description_ko' == '테스트'` |
| T_write_draft_count | 3개 concepts | `write_staging_draft(...)` | `return == 3` |

---

## G6: PipelineTaskImpl

### SDD

**파일**: `backend/app/usecases/pipeline_task_impl.py`

```python
class PipelineTaskImpl:
    """PipelineTask Protocol 구현체."""
    def __init__(self, llm: ILLMClient, pool: asyncpg.Pool): ...

    async def execute(self, session_id: str, doc_id: str, url: str) -> None:
        # 1. async with aiohttp.ClientSession() → fetch(url)
        # 2. chunk(crawl_result.content)
        # 3. extract_concepts(doc_id, chunks, self.llm)
        # 4. async with self.pool.acquire() as conn → write_staging_draft(...)
```

### TDD (AAA)

파일: `backend/tests/harness/test_pipeline_task_impl.py`

| ID | Arrange | Act | Assert |
|----|---------|-----|--------|
| T_impl_protocol | `PipelineTaskImpl(mock_llm, pool)` | `isinstance(impl, PipelineTask)` | `True` |
| T_impl_writes_draft | mock fetch + mock LLM, asyncpg_pool | `impl.execute(sid, doc_id, url)` | staging_concepts에 DRAFT 행 ≥ 1 |
| T_impl_crawl_error | fetch → ClientError | `impl.execute(...)` | `raises` or logs, staging 행 0 |

---

## G7: Staging Gate API 완성

### SDD

**수정 파일**: `backend/app/interfaces/api/staging.py`

추가할 엔드포인트:

```
GET   /{session_id}              → DRAFT 목록 반환 (list[dict])
POST  /{session_id}/reject       → 전체 DRAFT 삭제, {"rejected": N}
GET   /{session_id}/diff         → {"draft": N, "approved": M, "committed": K}
PATCH /{session_id}/nodes/{node_id} → 개별 APPROVED/REJECTED 전환
```

### TDD (AAA)

파일: `backend/tests/harness/test_staging_api.py`

| ID | Arrange | Act | Assert |
|----|---------|-----|--------|
| T_get_staging_list | 2행 DRAFT insert | `GET /{session_id}` | 200, `items` 길이 2 |
| T_reject_clears_draft | 3행 DRAFT | `POST /{session_id}/reject` | 200, `{"rejected":3}`, DB 행 0 |
| T_diff_counts | 2 DRAFT + 1 APPROVED | `GET /{session_id}/diff` | `{"draft":2,"approved":1,"committed":0}` |

---

## G8: GraphWriter

### SDD

**파일**: `backend/app/infrastructure/graph/graph_writer.py`

```python
DOMAIN_TAG_MAP = {
    "security":    ["security"],
    "performance": ["performance"],
    "both":        ["security", "performance"],
}

async def write_concept_node(
    concept: ConceptExtractionSchema,
    driver: neo4j.AsyncDriver,
) -> None:
    # MERGE (c:Concept {name: concept.concept_name})
    # ON CREATE SET aliases, cwe_id, description_ko, created_at
    # ON MATCH  SET updated_at
    # UNWIND DOMAIN_TAG_MAP[concept.concept_domain]
    #   MERGE (t:Tag {name: tag_name})
    #   MERGE (c)-[:TAGGED_WITH]->(t)
```

### TDD (AAA)

파일: `backend/tests/harness/test_graph_writer.py`

| ID | Arrange | Act | Assert |
|----|---------|-----|--------|
| T_gw_merge_idempotent | neo4j_driver | `write_concept_node(xss)` × 2회 | `MATCH (c:Concept{name:"XSS"}) count == 1` |
| T_gw_security_tag | `concept_domain="security"` | `write_concept_node(concept)` | `(:Concept)-[:TAGGED_WITH]->(:Tag{name:"Security"})` 존재 |
| T_gw_both_tags | `concept_domain="both"` | `write_concept_node(concept)` | Security + Performance 태그 각 1개 |
| T_gw_aliases | `aliases=["Cross-Site Scripting"]` | `write_concept_node(concept)` | `c.aliases` contains alias |

---

## G9: commit_staging

### SDD

**파일**: `backend/app/usecases/commit_staging.py`

```python
async def commit_staging(
    session_id: str,
    conn: asyncpg.Connection,
    driver: neo4j.AsyncDriver,
) -> int:
    # 1. SELECT ... FOR UPDATE — APPROVED 행 잠금
    # 2. concept_json → ConceptExtractionSchema
    # 3. concepts 테이블 UPSERT (concept_name UNIQUE)
    # 4. write_concept_node(concept, driver)
    # 5. UPDATE staging_concepts SET status='COMMITTED'
    # 반환: committed 행 수
```

### TDD (AAA)

파일: `backend/tests/harness/test_commit_staging.py`

| ID | Arrange | Act | Assert |
|----|---------|-----|--------|
| T_commit_writes_concepts | 2행 APPROVED staging | `commit_staging(sid, conn, driver)` | `concepts` 테이블 2행 |
| T_commit_status_committed | 2행 APPROVED | `commit_staging(...)` | staging 모두 `COMMITTED` |
| T_commit_neo4j | XSS APPROVED | `commit_staging(...)` | Neo4j `Concept{name:"XSS"}` 존재 |
| T_commit_zero | 0행 APPROVED | `commit_staging(...)` | return 0, 예외 없음 |

---

## G10: LinkResolver

### SDD

**파일**: `backend/app/usecases/link_resolver.py`

```python
async def find_same_as_candidates(
    concept_name: str,
    aliases: list[str],
    driver: neo4j.AsyncDriver,
) -> list[str]:
    # MATCH (c:Concept) WHERE c.name IN aliases
    #   OR any(a IN c.aliases WHERE a IN aliases)
    # AND c.name <> concept_name
    # RETURN c.name

async def create_same_as_relation(
    name_a: str, name_b: str,
    driver: neo4j.AsyncDriver,
) -> None:
    # MERGE (a:Concept{name:$a})-[:SAME_AS]-(b:Concept{name:$b})
```

### TDD (AAA)

파일: `backend/tests/harness/test_link_resolver.py`

| ID | Arrange | Act | Assert |
|----|---------|-----|--------|
| T_resolver_finds_alias | Neo4j에 `Concept{name:"XSS", aliases:["Cross-Site Scripting"]}` | `find_same_as_candidates("CrossSiteScripting", ["Cross-Site Scripting"], driver)` | `"XSS" in result` |
| T_resolver_no_match | 관련 없는 노드들 | `find_same_as_candidates("Unknown", [], driver)` | `result == []` |
| T_resolver_creates_rel | XSS, Alt 두 노드 | `create_same_as_relation("XSS","Alt", driver)` | `SAME_AS` 관계 1개 |

---

## 구현 순서

```
G1 → G2 → G3 → G4 → G5 → G6 → G7 → G8 → G9 → G10
```

각 단계: **SDD 확인 → 테스트 파일 작성 → `pytest` 실패 확인 → 구현 → `pytest` 통과 → 커밋** -->
