# CodeSheppard — Backend Specification
# Phase 1: MVP (단일 RAGAS 루프) → Phase 2: Multi-Agent (3-에이전트 파이프라인)
# 이 파일은 백엔드 구현에 필요한 모든 사양을 담고 있습니다.

---

## 전제 조건 — 반드시 읽고 시작할 것

> **작업 경로 제한**
> 백엔드 파일은 아래 경로 안에서만 생성하거나 수정한다.
>
> ```
> backend/m4/
> ```
>
> 이 경로 밖의 파일(api-core, _shared, m0~m3, m5 등)은
> 절대 수정하지 않는다.
> 단, 공용 모듈(_shared, api-core)을 import해서 읽는 것은 허용한다.
> 공용 모듈을 수정해야 할 필요가 생기면 사용자에게 먼저 확인 후 진행한다.

---

## 0. AI 모델 설정 (Gemini API)

| 역할 | 모델 | 용도 |
|------|------|------|
| 빠르고 저렴한 LLM | `gemini-2.5-flash` | Curator Agent, Builder Agent, 카드 생성 |
| 고성능 LLM | `gemini-2.5-pro` | Validator Agent (RAGAS 평가) |
| 임베딩 | `bge-m3` (Ollama 로컬) — Phase 1 | embed_query() — **현재 확인 완료**: `EMBEDDING_PROVIDER=ollama`, `OLLAMA_EMBEDDING_MODEL=bge-m3`, **1024차원** (실제 Cloud SQL `chunk_embeddings.embedding` 컬럼 확인, `.env` 설정됨). KMS 문서 임베딩과 **반드시 동일 모델 사용** (코딩 에이전트 아웃풋을 embed_query()로 벡터화 → chunk_embeddings 유사도 검색). **Google Cloud 전환 시**: `text-multilingual-embedding-002`(768차원)로 변경 예정 → `chunk_embeddings` 재생성 + `PGVECTOR_DIMENSION=768` 변경 필요 |

SDK: `google-generativeai` (Python)

---

## 1. 핵심 결정 사항 — Phase 1 (MVP)

| 결정 | 내용 |
|-----|-----|
| D1 | LangGraph 제거 → 단순 함수 파이프라인 (learn_pipeline.py) |
| D2 | 비동기 파이프라인 + status polling (POST /api/learn → 202) |
| D3 | user_id = **JWT Bearer 토큰**에서 추출 (`shared.auth.get_current_user` 의존성). `pull_requests.user_id` (UUID)는 `users.user_id` 참조 (docs/ddl.md §11). ~~teams.team_id 아님~~ **ASSUMPTION**: JWT `sub` 클레임 → `pull_requests.user_id` 매핑 경로 확인 필요 (cs_users.id → users.user_id 연결 방식) |
| D4 | curriculum_plan UNIQUE(issue_id) + ON CONFLICT |
| D5 | curriculum_plan에 llm_fallback BOOLEAN + status TEXT 추가 |
| D6 | curriculum_plan에 error_message TEXT 추가 |
| D7 | pytest 단위테스트 4개 우선 (E2E는 Phase 2) |
| D8 | FastAPI BackgroundTasks (Celery는 Phase 2) |
| D9 | `chunk_embeddings` HNSW 인덱스 — 기존 테이블에 이미 존재 (docs/ddl.md §5). 별도 추가 불필요 |
| D10 | 트리거 = 웹페이지 팝업 모달. scan_id 없음, 서버가 최신 PR 자동 조회 |
| D11 | 카드 페이지 로드 시 자동 POST /api/complete (별도 완료 버튼 없음) |
| D12 | github_comment_id 저장 불필요 |
| D13 | pull_requests 컬럼: id(UUID), user_id(UUID) — **users.user_id 참조** (teams.team_id 아님, 수정됨), week_id, github_pr_url, github_pr_number, status, coverage, is_lgtm, submitted_at, repository_full_name. 실제 모델: `backend/api-core/app/models/pull_request.py` |
| D14 | ragas_eval() 반환값에 reason 필드 설계 — Phase 1은 None, Phase 2에서 전략 분기에 활용 |
| D15 | RAG 결과 2개 미만이면 domain 제거 후 1회 재시도 (룰 기반). Phase 2에서 Curator가 교체 |
| D16 | 카드 타입 분기(개념 설명 / 코드 수정)는 Phase 1에서 조건문. Phase 2에서 Curator 출력으로 교체 |
| D17 | 아키텍처 문서는 이 파일에 Phase 1 / Phase 2 섹션으로 구분 |
| D18 | 카드 깊이 개인화 — Phase 1: severity in [critical, high] OR mistake_count >= 3 이면 DEEP, 그 외 QUICK. mistake_count = review_issue 테이블에서 user_id + keyword 기준 집계 (Section 8 참조). Phase 2: Curator 동적 결정 |
| D19 | 서버가 user_id로 최신 pull_request 조회 → review_issues severity top 3 자동 선택 → 카드 3개 생성 |
| D20 | 팝업 UX — "학습하기" → "학습을 시작하겠습니까?" → 예 클릭 → POST /api/learn |
| D21 | KMS 사내문서는 오프라인 사전 임베딩 → `chunk_embeddings` 저장 (doc_chunk 없음). `scripts/embed_kms_docs.py`로 직접 임베딩 완료 (2026-06-06). 이후 변경 없음 |
| D34 | mock 데이터 없음 — review_issue는 Cloud SQL(PostgreSQL)에 직접 INSERT하여 실제 DB 조회. USE_MOCK_LLM 플래그 사용 안 함 |
| D35 | Gemini API 실제 호출 — `GEMINI_API_KEY` .env에 필수. 카드 생성(gemini-2.5-flash) + RAGAS judge(gemini-2.5-pro) |
| D36 | 에이전트 실행 결과·검증 결과·평가 로그 모두 Cloud SQL(PostgreSQL) 저장. Section 20 테이블 목록 참조 |
| D28 | 코딩 에이전트 인풋 스키마 — github_id, scan_id, agent, severity, keyword, sub_category, code_context, code_snippet, suggestion, programming_language, framework, framework_version, name_of_function, reviewed_date |
| D29 | RAG 검색 2개 분리 — 검색1(개념): keyword+sub_category+code_context+framework+version / 검색2(코드예제): keyword+sub_category+code_snippet |
| D30 | 검색1·검색2 모두 결과 없으면 LLM 자체 생성 fallback (llm_fallback=True) |
| D31 | reviewed_date = 코딩 에이전트가 이슈를 발견한 날짜. pull_requests.submitted_at과 다른 개념 |
| D32 | code_context = 이 코드가 어떤 기능을 하는지 설명. 검색1 쿼리 + 카드 표시 양쪽 활용 |
| D33 | rag_search()는 SearchAdapter 추상 인터페이스 뒤에 구현. Phase 1: PgvectorAdapter. TODO-4 결과 후 FTSAdapter/HybridAdapter 교체 가능 |

---

## 2. 핵심 결정 사항 — Phase 2 (Multi-Agent)

| 결정 | 내용 |
|-----|-----|
| D22 | Curator Agent (gemini-2.5-flash) — 개발자 프로필 + 이슈 → {depth, focus, analogy, key_points, card_type, query_fields} |
| D23 | Builder Agent (gemini-2.5-flash) — curator_instruction 받아 카드 생성. build_card() 시그니처에 파라미터 추가 (하위 호환) |
| D24 | Validator Agent (gemini-2.5-pro + RAGAS) — reason 필드 채워서 반환 |
| D25 | 에이전트 간 통신 — 함수 파이프라인 (message passing). 공유 상태 없음 |
| D26 | Phase 2 재시도 전략 — reason 기반 Curator 재지시 후 RAG 재검색 포함 |
| D27 | Curator 비용 — gemini-2.5-flash 추가 1회 ≈ $0.0001/카드 수준. 카드 3개 기준 ~$0.0003 추가 |

---

## 3. DB 스키마 수정

```sql
-- [신규 테이블] curriculum_plan: 현재 DDL에 없음 → m4 Alembic 마이그레이션으로 생성 필요
-- 기존 curriculums/curriculum_weeks 테이블(docs/ddl.md §8,9)과 별개:
--   curriculums: 전체 커리큘럼 헤더 (M4 /curriculum 엔드포인트 output)
--   curriculum_plan: PR 이슈별 학습 카드 단위 (이 스펙의 학습 카드 생성 파이프라인용)
--
-- Phase 1: curriculum_plan 컬럼 추가
ALTER TABLE curriculum_plan ADD COLUMN status TEXT DEFAULT 'pending';
  -- 'pending' | 'running' | 'completed' | 'failed'
ALTER TABLE curriculum_plan ADD COLUMN llm_fallback BOOLEAN DEFAULT FALSE;
ALTER TABLE curriculum_plan ADD COLUMN error_message TEXT;
ALTER TABLE curriculum_plan ADD CONSTRAINT curriculum_plan_issue_id_unique UNIQUE (issue_id);

-- [수정] doc_chunk 테이블 없음 → 기존 chunk_embeddings 테이블 사용 (docs/ddl.md §5)
-- chunk_embeddings에 HNSW 인덱스 이미 존재:
--   CREATE INDEX idx_chunk_embeddings_hnsw ON chunk_embeddings USING hnsw (embedding vector_cosine_ops);
-- 카테고리 필터는 chunk_embeddings.metadata JSONB 필드 사용:
--   metadata @> '{"category": "보안"}'
--   또는 metadata->>'category' = '보안'
-- category 값 정의 (기존 documents.category와 별개, T11에서 실제 데이터 분포 확인 후 확정):
--   '보안'        : 보안/도메인 공식문서 → 검색 1 대상 (9개 청크)
--   '코딩컨벤션'  : 사내 코딩 컨벤션 자료 → 검색 2 대상 (55개 청크)
--   '코드성능검증': 심화 학습 자료        → 검색 3 대상 (1개 청크, placeholder — D15 fallback 상시 발동)

-- Phase 2: curriculum_plan에 Curator 결과 저장
ALTER TABLE curriculum_plan ADD COLUMN curator_instruction JSONB;
  -- {"depth": "deep", "focus": "...", "analogy": "...", "key_points": [...], "card_type": "concept"}
ALTER TABLE curriculum_plan ADD COLUMN ragas_reason TEXT;
  -- "low_faithfulness" | "low_relevancy" | null
ALTER TABLE curriculum_plan ADD COLUMN attempt_count INTEGER DEFAULT 0;

-- [신규 테이블] review_issue: 코딩 에이전트 인풋 전체 저장 (D28, D31)
-- 현재 DDL에 없음 → m4 Alembic 마이그레이션으로 생성 필요
-- 기존 scan_issues 테이블(docs/ddl.md §13)과 별개: scan_issues는 m2/m3 스캔 결과,
-- review_issue는 코딩 에이전트의 상세 인풋(code_snippet, framework 등) 저장용
-- NOTE: severity 값이 scan_issues(Critical/Major/Minor)와 다름(critical/high/medium/low)
--       → ASSUMPTION: 코딩 에이전트가 m2/m3와 별도로 이 테이블을 직접 채우는 구조
ALTER TABLE review_issue ADD COLUMN agent TEXT;
ALTER TABLE review_issue ADD COLUMN code_context TEXT;
ALTER TABLE review_issue ADD COLUMN code_snippet TEXT;
ALTER TABLE review_issue ADD COLUMN suggestion TEXT;
ALTER TABLE review_issue ADD COLUMN programming_language TEXT;
ALTER TABLE review_issue ADD COLUMN framework TEXT;
ALTER TABLE review_issue ADD COLUMN framework_version TEXT;
ALTER TABLE review_issue ADD COLUMN name_of_function TEXT;
ALTER TABLE review_issue ADD COLUMN reviewed_date TIMESTAMPTZ;
```

**DB 구조 핵심**
- `pull_requests.id` (UUID) = `scan_id`
- `pull_requests.user_id` (UUID) = `users.user_id` (docs/ddl.md §11). **teams.team_id가 아님** (수정됨)
- 인증: `Authorization: Bearer <JWT>` 헤더 → `shared.auth.get_current_user` → JWT `sub` 클레임
- **ASSUMPTION**: JWT `sub` → `pull_requests.user_id` 매핑 확인 필요 (api-core auth 흐름 참조)
- `curriculum_plan`, `review_issue` 테이블: 현재 DDL에 없음 → m4 신규 Alembic 마이그레이션 필요

---

## 4. 코딩 에이전트 인풋 스키마 (POST /api/ingest)

```json
{
  "github_id": "string",
  "scan_id": "uuid",
  "agent": "string",
  "severity": "critical|high|medium|low",
  "keyword": "string",
  "sub_category": "string",
  "code_context": "string",
  "code_snippet": "string",
  "suggestion": "string",
  "programming_language": "string",
  "framework": "string",
  "framework_version": "string",
  "name_of_function": "string",
  "reviewed_date": "ISO8601"
}
```

---

## 5. RAG 검색 3개 설계 (D29, D30, D33)

### embed_query() 구현 방식

review_issue 컬럼 데이터를 `컬럼명: 값` 형식으로 조합 후 bge-m3로 임베딩.
(단순 공백 concatenate보다 bge-m3가 각 필드의 의미를 더 잘 파악함)

```python
# app/kms/search_adapter.py

def build_search1_text(issue) -> str:
    # 검색1: keyword + sub_category + code_context
    parts = []
    if issue.keyword:       parts.append(f"keyword: {issue.keyword}")
    if issue.sub_category:  parts.append(f"sub_category: {issue.sub_category}")
    if issue.code_context:  parts.append(f"code_context: {issue.code_context}")
    return " ".join(parts)
# → "keyword: SQL Injection sub_category: input validation code_context: 상품 검색 기능 — 사용자 입력을 쿼리에 직접 삽입"

def build_search2_text(issue) -> str:
    # 검색2: keyword + sub_category + code_snippet(있으면) + programming_language + framework + framework_version
    parts = []
    if issue.keyword:              parts.append(f"keyword: {issue.keyword}")
    if issue.sub_category:         parts.append(f"sub_category: {issue.sub_category}")
    if issue.code_snippet:         parts.append(f"code_snippet: {issue.code_snippet[:300]}")
    if issue.programming_language: parts.append(f"language: {issue.programming_language}")
    if issue.framework:            parts.append(f"framework: {issue.framework}")
    if issue.framework_version:    parts.append(f"version: {issue.framework_version}")
    return " ".join(parts)
# → "keyword: SQL Injection sub_category: input validation code_snippet: def search(kw): ... language: Python framework: FastAPI version: 0.104.0"

def build_search3_text(issue) -> str:
    # 검색3: keyword + sub_category + programming_language + framework + version + code_snippet(있으면)
    parts = []
    if issue.keyword:              parts.append(f"keyword: {issue.keyword}")
    if issue.sub_category:         parts.append(f"sub_category: {issue.sub_category}")
    if issue.programming_language: parts.append(f"language: {issue.programming_language}")
    if issue.framework:            parts.append(f"framework: {issue.framework}")
    if issue.framework_version:    parts.append(f"version: {issue.framework_version}")
    if issue.code_snippet:         parts.append(f"code_snippet: {issue.code_snippet[:300]}")
    return " ".join(parts)
# → "keyword: SQL Injection sub_category: input validation language: Python framework: FastAPI version: 0.104.0 code_snippet: def search(kw): ..."

async def embed_query(query_text: str) -> list[float]:
    # bge-m3 (Ollama) → 1024차원 벡터. KMS 문서 임베딩과 반드시 동일 모델 사용
    response = await httpx.AsyncClient().post(
        f"{OLLAMA_BASE_URL}/api/embeddings",
        json={"model": OLLAMA_EMBEDDING_MODEL, "prompt": query_text}
    )
    return response.json()["embedding"]
```

```python
# SearchAdapter 인터페이스 (D33) — Phase 1: PgvectorAdapter 사용
# TODO-4 결과 후 FTSAdapter / HybridAdapter 교체 가능 (pipeline 코드 변경 없음)

# 검색 1 — 개념 설명 문서 (category='보안')
# category 필터: chunk_embeddings.metadata @> '{"category": "<값>"}' (JSONB 쿼리)
docs_concept = rag_search(await embed_query(build_search1_text(issue)),
    category='보안')
if len(docs_concept) == 0:
    docs_concept = None  # → LLM 자체 생성 fallback

# 검색 2 — 코드 예제 문서 (category='코딩컨벤션')
# code_snippet 없는 경우: metadata 기반 쿼리로 대체 (before_code = null)
if issue.code_snippet:
    docs_example = rag_search(embed_query(
        keyword, sub_category, code_snippet
    ), category='코딩컨벤션')
else:
    # code_snippet 없음 → name_of_function 등 메타데이터로 검색
    docs_example = rag_search(embed_query(
        keyword, sub_category, code_context,
        programming_language, framework, framework_version
    ), category='코딩컨벤션')
if len(docs_example) == 0:
    docs_example = None  # → LLM 자체 생성 fallback

# 검색 3 — 학습 추천 문서 (category='코드성능검증')
docs_recommend = rag_search(embed_query(
    keyword, sub_category, code_context,
    suggestion, programming_language,
    framework, framework_version
), category='코드성능검증')  # → chunk_embeddings.metadata->>'category' = '코드성능검증'
if len(docs_recommend) == 0:
    docs_recommend = None  # → LLM 자체 추천 fallback (섹션 표시는 유지)

card = build_card(
    issue=issue,
    docs_concept=docs_concept,
    docs_example=docs_example,
    docs_recommend=docs_recommend,
    depth=depth
)
# before_code: code_snippet 없으면 null (프론트에서 단일 컬럼 렌더링)
card["before_code"] = issue.code_snippet or None
llm_fallback = (docs_concept is None or docs_example is None)
# llm_fallback=True이면 RAGAS 평가 스킵 → Section 6 참조
```

| | 검색 1 | 검색 2 | 검색 3 |
|--|--------|--------|--------|
| 임베딩 입력 | keyword + sub_category + code_context | keyword + sub_category + code_snippet(있으면) + programming_language + framework + version | keyword + sub_category + programming_language + framework + version + code_snippet(있으면) |
| 문서 카테고리 | `보안` (chunk_embeddings.metadata->>'category') | `코딩컨벤션` | `코드성능검증` |
| 찾는 것 | "왜 이 패턴이 나쁜가" 개념 | 컨벤션에 맞는 올바른 코드 작성 방법 | 코드 성능 검증 관련 자료 |
| 카드 활용 | 설명 섹션 + 왜 위험한가 + 왜 중요한가 | After 코드 생성 근거 | 학습 추천 섹션 |
| Before 코드 | — | code_snippet 인풋 그대로 (RAG/LLM 없음) | — |
| After 코드 | — | RAG → 컨벤션 기반 LLM 수정 | — |
| fallback | LLM 자체 생성 | LLM 자체 생성 | LLM 일반 추천 (섹션 유지) |

**chunk_embeddings.metadata 카테고리** (doc_chunk 없음 → chunk_embeddings 사용)
- `보안` — 보안/도메인 공식문서 → 검색 1
- `코딩컨벤션` — 사내 코딩 컨벤션 → 검색 2
- `코드성능검증` — 코드 성능 검증 관련 자료/가이드 → 검색 3
- Phase 1: `scripts/embed_kms_docs.py`로 직접 삽입 (Section 19-3 참조)

---

## 6. Phase 1: RAGAS 평가 루프

**구현 방식**: RAGAS Python 라이브러리 + Gemini judge
```
pip install ragas
judge LLM: gemini-2.5-pro (Section 0 참조)
측정 지표: faithfulness, answer_relevancy
입력 형식: question(keyword), contexts(docs 청크 리스트), answer(card 본문)
```

```python
from ragas.metrics import faithfulness, answer_relevancy
from ragas.llms import LangchainLLMWrapper
# Gemini를 RAGAS judge LLM으로 설정 (requirements.txt에 ragas 추가)

def ragas_eval(card: dict, docs: list[str]) -> dict:
    # question = keyword (무엇을 물어봤는가)
    # contexts = docs (3개 검색 결과 합산: docs_concept + docs_example + docs_recommend)
    # answer = card["explanation"] + card["core_summary"]
    score = evaluate_with_ragas(question, contexts, answer)
    passed = (score["faithfulness"] >= 0.7 and score["answer_relevancy"] >= 0.7)
    return {"passed": passed, "reason": None}  # reason은 Phase 2에서 채움 (D14)

# llm_fallback=True이면 RAGAS 스킵 — docs 없으면 faithfulness 측정 대상 없음
if not llm_fallback:
    # docs 3개 합산해서 RAGAS contexts로 전달
    all_docs = [*(docs_concept or []), *(docs_example or []), *(docs_recommend or [])]
    for attempt in range(3):
        card = build_card(query, depth=depth)
        result = ragas_eval(card, all_docs)
        if result["passed"]:
            break
        # Phase 1: 동일 전략 재시도 (reason=None이므로 전략 변경 없음)
        # Phase 2: result["reason"] 기반 Curator 재지시
    else:
        # 3회 실패 → fallback_card(), llm_fallback=True
        card = fallback_card(query)
        llm_fallback = True
```

**임계값**: faithfulness ≥ 0.7, answer_relevancy ≥ 0.7

> **[m4 자체 추가 / spec 외] `SKIP_RAGAS_EVAL` 플래그** — `.env`의 `SKIP_RAGAS_EVAL=true`로 설정하면
> `generate_card()`가 RAGAS 평가 루프(gemini-2.5-pro judge 호출, attempt당 2~4초·API 비용 발생)를 건너뛰고
> `build_card()` 결과를 그대로 사용한다. `llm_fallback=True`일 때(D30, docs 없음)와 동일하게 처리되며,
> `llm_fallback` 값은 변경하지 않는다(평가를 안 했을 뿐 RAG 자체는 정상 수행됨을 구분).
> 개발/테스트 단계에서 RAGAS 호출 비용을 줄이기 위한 cost-control 용도 — 기본값은 `false`(spec 기본 동작 유지).
> 구현: `app/pipeline/learn_pipeline.py`의 `_skip_ragas_eval()`

---

## 7. Phase 2: 3-에이전트 파이프라인

```
issue + developer_profile
    │
    ▼
Curator Agent (gemini-2.5-flash)
  입력: profile.weak_categories, issue.severity/keyword, past_mistakes, optional hint
  출력: { depth, focus, analogy, key_points, card_type, query_fields }
    │
    │ curator_instruction
    ▼
embed_query(curator.query_fields)  ← text-multilingual-embedding-002
    │
    ▼
rag_search()
    │
    └── for attempt in range(3):
            │
            ▼
        Builder Agent (gemini-2.5-flash)
          입력: docs + curator_instruction
          출력: card_content
            │
            ▼
        Validator Agent (gemini-2.5-pro + RAGAS)
          faithfulness ≥ 0.7?  answer_relevancy ≥ 0.7?
          출력: { passed: bool, reason: str | None }
            │
     ┌──────┴──────────────────────────────┐
     │ passed                               │ failed
     ▼                                      ▼
curriculum_plan 저장             reason 기반 Curator 재지시
status='completed'               "low_faithfulness" → hint="narrow_query" → RAG 재검색
                                 "low_relevancy"    → hint="change_framing" → Builder 재생성
                                 attempt 3 → fallback_card()
```

**Phase 2 재시도 로직**
```python
if result["reason"] == "low_faithfulness":
    curator_instruction = curator_agent(profile, issue, hint="narrow_query")
    docs = rag_search(embed_query(**curator_instruction["query_fields"]))
elif result["reason"] == "low_relevancy":
    curator_instruction = curator_agent(profile, issue, hint="change_framing")
```

---

## 8. 카드 깊이 결정 (D18)

```python
# Phase 1 (T10): 조건문
# mistake_count = 이 개발자(user_id)가 같은 keyword로 발생시킨 이슈 총 횟수
# 별도 테이블 불필요 — review_issue.user_id 기준 집계로 충분
mistake_count = (
    db.query(ReviewIssue)
    .filter(
        ReviewIssue.user_id == user_id,   # 이 개발자만
        ReviewIssue.keyword == issue.keyword
    )
    .count()
)

depth = "deep" if (
    issue.severity in ["critical", "high"] or
    mistake_count >= 3
) else "quick"

# Phase 2: 이 조건문을 Curator 에이전트가 대체
```

---

## 9. top 3 자동 선택 로직 (D19)

```python
user_id = current_user["sub"]  # JWT sub 클레임 → users.user_id (UUID)

latest_pr = (
    db.query(PullRequest)
    .filter(PullRequest.user_id == user_id)
    .order_by(PullRequest.submitted_at.desc())
    .first()
)

top3 = (
    db.query(ReviewIssue)
    .filter(ReviewIssue.pull_request_id == latest_pr.id)
    .order_by(
        case({"critical": 4, "high": 3, "medium": 2, "low": 1}, value=ReviewIssue.severity).desc()
    )
    .limit(3).all()
)
```

---

## 10. API 사양

> **m4 서비스 URL**: docker-compose 내부 `http://m4:8005`, 로컬 개발 `http://localhost:8005`  
> **인증**: 모든 엔드포인트에 `Authorization: Bearer <JWT>` 헤더 필수 (`shared.auth.get_current_user`)  
> **기존 엔드포인트 유지**: `POST /evaluate`, `POST /curriculum` (m1 orchestrator 호출용) — 변경 없음

### POST /api/ingest
```
review_issue 저장 (코딩 에이전트 → 서버)
현재 상태: 코딩 에이전트 미연동 → Phase 1은 Cloud SQL review_issue 테이블에 직접 INSERT하여 테스트 (D34)
```

### POST /api/learn
```
Request:  {}   (body 없음 — user_id는 JWT에서 추출)
Response: 202 { scan_id: uuid, plan_ids: [uuid1, uuid2, uuid3] }
  -- scan_id = pull_requests.id (프론트가 GET /api/pr/{scan_id} polling에 사용)
중복:     200 + 기존 { scan_id, plan_ids } (D4 ON CONFLICT)
PR 없음:  404 { detail: "제출된 PR이 없습니다. PR을 먼저 제출해 주세요." }
  -- 프론트는 404 수신 시 에러 대신 안내 화면 렌더링 (FRONTEND_SPEC Section 8 참조)

서버 내부:
  JWT Bearer → user_id (users.user_id UUID) → 최신 PR (pull_requests 테이블 직접 조회)
  → severity top 3 이슈 (review_issue 테이블 — Cloud SQL 직접 조회)
  → asyncio.gather(*[generate_card(issue) for issue in top3])  # 카드 3개 병렬
  → 202 즉시 반환 (BackgroundTask 내부에서 gather 실행)
```

### GET /api/pr/{scan_id}
```json
{
  "issues": [{
    "id": "uuid",
    "keyword": "SQL Injection",
    "severity": "critical",
    "plan": {
      "id": "uuid",
      "status": "pending|running|completed|failed",
      "llm_fallback": false,
      "error_message": null,
      "card_content": {},
      "ragas_reason": "low_faithfulness|low_relevancy|null",
      "attempt_count": 2,
      "curator_instruction": {}
    }
  }]
}
```
  -- card_content: status=completed일 때만 존재 (그 외 null)

### POST /api/complete
```
Request:  { plan_id }
Response: 200 { id, completed_at }
중복 완료: idempotent
```

---

## 11. 디렉토리 구조

```
backend/m4/
├── app/
│   ├── __init__.py
│   ├── main.py                    ← 기존 /evaluate, /curriculum + 신규 /api/* 라우터 등록
│   ├── api/
│   │   └── routes.py              ← /api/learn, /api/pr/{scan_id}, /api/complete (top 3 선택 포함)
│   ├── pipeline/
│   │   ├── learn_pipeline.py      ← Phase 1: 카드 타입 분기 + RAG + RAGAS 루프
│   │   ├── learn_pipeline_v2.py   ← Phase 2: 3-에이전트 파이프라인
│   │   ├── card_router.py         ← Phase 1: concept / code_fix 필드 정의
│   │   ├── curator_agent.py       ← Phase 2: T11
│   │   └── prompts.py             ← DEEP/QUICK 프롬프트 + curator 기반 동적 프롬프트
│   ├── kms/
│   │   └── search_adapter.py      ← SearchAdapter 인터페이스 + Adapters (D33)
│   ├── models/
│   │   ├── curriculum_plan.py     ← curriculum_plan SQLAlchemy 모델 (m4 신규)
│   │   └── review_issue.py        ← review_issue SQLAlchemy 모델 (m4 신규)
├── alembic/
│   ├── env.py                     ← 기존 (shared.db.Base 기준)
│   └── versions/
│       ├── 0001_m4_tables.py      ← curriculum_plan + review_issue 신규 생성 (T1)
│       └── 0002_multiagent.py     ← Phase 2: curator_instruction, ragas_reason (T16)
├── tests/
│   ├── test_contract.py           ← 기존 /evaluate, /curriculum 계약 테스트 (유지)
│   ├── test_pipeline.py           ← Phase 1 단위 테스트 (T7)
│   ├── test_api.py                ← API 테스트 (T7)
│   └── test_multiagent_pipeline.py ← Phase 2 통합 테스트 (T15)
├── scripts/
│   ├── embed_kms_docs.py          ← KMS 문서 직접 임베딩 스크립트 (Section 19 참조)
│   ├── create_eval_dataset.py     ← TODO-4: RAGAS ground truth 생성
│   └── kms_benchmark.py           ← TODO-4: 3개 백엔드 비교
├── BACKEND_SPEC.md
├── Dockerfile
├── pyproject.toml                 ← ragas, asyncpg, pgvector 추가 필요 (현재 없음)
└── uv.lock
```

> **pyproject.toml 추가 패키지 (현재 없음)**:
> ```toml
> dependencies = [
>     # 기존 유지
>     "fastapi>=0.111.0", "uvicorn[standard]>=0.30.0", "pydantic>=2.7.0",
>     "structlog>=24.2.0", "shared",
>     # m4 신규 추가 필요
>     "ragas",
>     "asyncpg",               # PostgreSQL 비동기 드라이버
>     "sqlalchemy[asyncio]",
>     "pgvector",              # pgvector Python 바인딩
>     "google-generativeai",   # Gemini API (또는 langchain-google-genai)
>     "python-jose[cryptography]",  # JWT (shared에서 사용 중)
> ]
> ```
> ⚠️ `asyncpg`, `httpx`, `python-dotenv`는 이미 추가됨. `ragas`, `pgvector`, `google-generativeai`는 T2 시작 전 추가 필요.

---

## 12. 구현 태스크 체크리스트

### Phase 1 — MVP (우선순위 순)

- [x] **T1 (P1, ~10min)** — DB 스키마 수정
  - curriculum_plan 신규 생성: status, llm_fallback, error_message, UNIQUE(issue_id)
  - review_issue 신규 생성: 코딩 에이전트 인풋 저장용
  - chunk_embeddings HNSW 인덱스: 이미 존재 (추가 불필요)
  - 확인: `psql \d curriculum_plan`

- [x] **T2 (P1, ~20min)** — 파이프라인 구현
  - learn_pipeline.py: 카드 타입 라우터 (D16) + RAG 재시도 룰 (D15) + BackgroundTasks
  - 확인: POST /api/learn → 202, status polling 작동
  - 구현 확인: `learn_pipeline.generate_card`/`route_card_type`/`build_card` 구현 완료, `test_pipeline.py` 통과 — 체크박스 갱신 누락이었음

- [x] **T3 (P1, ~15min)** — RAGAS 평가 루프
  - ragas_eval() 반환값: `{"passed": bool, "reason": None}`
  - for attempt in range(3): → 3회 실패 → fallback_card(), llm_fallback=True
  - 확인: 3회 실패 → fallback
  - 구현 확인: `learn_pipeline.ragas_eval` + `SKIP_RAGAS_EVAL` 플래그까지 구현, `test_ragas_all_3_fail_triggers_llm_fallback`/`test_ragas_passes_after_retry_stops_loop` 통과 — 체크박스 갱신 누락이었음

- [x] **T4 (P1, ~10min)** — JWT 인증 의존성 적용
  - `shared.auth.get_current_user` 의존성 활용 (별도 파일 불필요)
  - `api/routes.py` 각 엔드포인트에 `Depends(get_current_user)` 추가
  - JWT `sub` 클레임 → user_id (UUID) 추출
  - 확인: Bearer 토큰 없이 요청 시 401
  - 구현 확인: `routes.py`의 각 엔드포인트에 `Depends(get_current_user)` 적용, `test_post_learn_without_token_returns_401` 등 401 테스트 통과 — 체크박스 갱신 누락이었음

- [x] **T5 (P1, ~5min)** — UNIQUE + ON CONFLICT 처리
  - 동일 issue_id 재POST → 동일 plan_id 반환
  - 구현 확인: `routes.py`에 ON CONFLICT DO NOTHING 처리 구현, `test_post_learn_duplicate_returns_200_with_existing_plan_ids`/`test_post_learn_race_condition_returns_200_with_winner_plan_ids` 통과 — 체크박스 갱신 누락이었음

- [x] **T6 (P1, ~10min)** — 에러 핸들링 + error_message 저장
  - ⚠️ fallback_card() 실패 + DB write 실패 = SILENT GAP → try/except 필수
  - 실패 시 status='failed', error_message=str(e)
  - 구현: `generate_card()`에 build_card()/fallback_card() 호출을 감싸는 try/except 추가(embed_query 타임아웃과 동일 패턴),
    `_run_card_generation()`에 카드 생성+DB write 전체를 감싸는 catch-all try/except 추가 — 어떤 예외든 plan을 'failed'로 기록

- [x] **T7 (P1, ~10min)** — 단위 테스트 (Phase 1 P1)
  ```python
  # tests/test_pipeline.py
  test_ragas_all_3_fail_triggers_llm_fallback()
  test_pgvector_empty_result_triggers_fallback()
  test_rag_retries_without_domain_when_results_empty()
  test_embed_query_api_timeout_stores_error_message()
  test_build_card_success_returns_completed_plan()    # ← 추가: 정상 카드 생성 경로
  test_no_pull_request_returns_404_with_message()     # ← 추가: PR 없는 신규 개발자 → 404 + detail 메시지 확인
  test_build_card_without_code_snippet_uses_metadata_rag()  # ← 추가: code_snippet=None → metadata 검색 2 + before_code=null
  test_docs_none_skips_ragas_and_sets_llm_fallback()  # ← 추가: docs=None이면 RAGAS 스킵 + llm_fallback=True (D4)
  test_depth_is_deep_when_severity_critical()          # ← 추가: severity=critical → depth="deep" (D18)
  test_get_pr_scan_id_returns_correct_structure()      # ← 추가: GET /api/pr/{scan_id} 응답 JSON 구조 검증

  # tests/test_api.py
  test_duplicate_learn_returns_existing_plan()
  test_complete_duplicate_click_is_idempotent()
  ```
  - 구현 메모: 위 목록 중 `test_no_pull_request_returns_404_with_message`, `test_get_pr_scan_id_returns_correct_structure`,
    `test_duplicate_learn_returns_existing_plan`은 이름은 다르지만 `test_routes.py`의
    `test_post_learn_no_pr_returns_404` / `test_get_pr_returns_issues_with_plans` /
    `test_post_learn_duplicate_returns_200_with_existing_plan_ids`로 이미 동등하게 커버되어 있음을 확인.
    실제로 빠져 있던 두 케이스 `test_depth_is_deep_when_severity_critical`(test_pipeline.py)과
    `test_complete_duplicate_click_is_idempotent`(test_routes.py, `_mark_plan_completed` 직접 호출로 idempotent 분기 검증)를
    추가해 27→28개 테스트로 보강 완료. 두 함수 모두 이미 올바르게 구현돼 있어 테스트 추가만으로 즉시 GREEN(회귀 방지 테스트 성격).

<!-- 그래서 "pull_requests 조회 → top3 선택" 파이프라인은 T9에서 따로 만들 일 -->
- [x] **T9 (P1, ~20min)** — 웹페이지 팝업 모달 + top 3 자동 선택
  - 서버: latest PR → severity top 3 선택 로직 (위 9번 코드 참조)
  - 확인: 팝업 예 클릭 → 카드 3개 표시
  - 진행 상황: 서버(`_find_latest_pr_id`/`_find_top3_issues`)와 프론트 팝업(`LearningModal`/`LearningPage` — 모달 자동 표시 + 예/아니오 닫기)은 완료.
    프론트 API 연동은 3개 TDD 슬라이스로 분할 진행해 모두 완료 (FRONTEND_SPEC Section 2/3/10):
    - [x] Slice 1 — "예" 클릭 → `m4Api.post('/api/learn', {})` 호출 + 로딩 상태 표시.
      `pages/learning/lib/m4Api.ts` 신규 생성(별도 axios 인스턴스, JWT 인터셉터, `VITE_M4_URL` 베이스).
      `LearningPage.test.tsx`에 `vi.mock`으로 m4Api를 모킹한 RED→GREEN 테스트 추가 (전체 24/24 통과)
    - [x] Slice 2 — `GET /api/pr/{scan_id}` 폴링 (2초 간격, 이슈별 독립 status, 모두 종료 상태가 되면 중단).
      `pages/learning/hooks/useLearningApi.ts` 신규 생성 (재귀 `setTimeout` 방식, `renderHook`+`vi.useFakeTimers`로 검증)
    - [x] Slice 3 — 완료 카드 렌더링 (`LearningCard`/`CodeBlock`) + 자동 `POST /api/complete`.
      `pages/learning/components/LearningCard.tsx`/`CodeBlock.tsx` 신규 생성, `LearningPage`에서 `useLearningApi().issues`를 구독해 카드 목록 렌더링 (전체 35/35 통과)
    - [x] Slice 4 — `POST /api/learn` 실패 시 안내 화면 (FRONTEND_SPEC Section 8 "PR 없음 안내"/"그 외 에러" 보강).
      기존엔 `handleConfirm`에 try/catch가 없어 실패 시 "학습 카드를 생성하고 있어요..."에 멈춰있던 것을 수정 —
      404(PR 없음)면 "아직 등록된 PR이 없습니다" 안내, 그 외(network/500 등)면 "학습 카드를 불러오는 중 문제가
      발생했어요 / 잠시 후 다시 시도해주세요" 일반 오류 안내를 표시 (전체 37/37 통과)
  - [x] CORS — `app/main.py`에 `CORSMiddleware` 추가 (FRONTEND_SPEC Section 0: m4Api가 api-core 프록시를
    거치지 않고 `localhost:5173` → `localhost:8005`로 직접 cross-origin 호출하는데, 미들웨어가 없어
    preflight(OPTIONS)가 405로 막혀 브라우저에서 `net::ERR_FAILED` 발생하던 것을 수정.
    `allow_origins=["http://localhost:5173"]`로 허용 (백엔드 전체 40/40 통과)

- [x] **T10 (P2, ~10min)** — 카드 깊이 개인화 Phase 1
  - depth 조건문 (D18) + DEEP_CARD_PROMPT / QUICK_CARD_PROMPT 템플릿
  - 확인: severity=high → DEEP / severity=low + mistake_count<3 → QUICK
  - 구현 메모: `learn_pipeline.DEEP_CARD_PROMPT`/`QUICK_CARD_PROMPT` 템플릿을 분리해 depth에 따라 Builder Agent 지시문이 달라지도록 구현
    (DEEP은 "정보량을 늘리는 게 아니라 확실히 이해되도록 기초부터 차근차근 + 비유/예시 위주"로 설계 — 반복 실수 케이스에서 "더 어렵게"가 아니라 "더 쉽게 다시 설명"하는 방향).
    D18 mistake_count 임계값을 7 → 3으로 조정(논의 후 결정). `test_depth_is_deep_when_severity_high`,
    `test_depth_is_quick_when_severity_low_and_mistake_count_below_threshold`, `test_depth_is_deep_when_mistake_count_reaches_threshold`,
    `test_build_card_uses_deep_prompt_template_when_depth_is_deep`, `test_build_card_uses_quick_prompt_template_when_depth_is_quick` 추가, TDD RED→GREEN 확인 (33/33 통과)

### Phase 2 — Multi-Agent (Phase 1 완성 후)

- [x] **T11 (~30min)** — Curator 에이전트 (pipeline/curator_agent.py 신규)
  - 구현 완료: `curator_agent(profile, issue, hint=None)` — D22 계약대로 `{depth, focus, analogy, key_points, card_type, query_fields}` JSON 반환
  - `DeveloperProfile` TypedDict(weak_categories, past_mistakes), `CURATOR_PROMPT`/`CURATOR_MODEL_NAME`(gemini-2.5-flash) 정의
  - D26 재시도 전략 — hint="narrow_query"(low_faithfulness)/"change_framing"(low_relevancy)에 따라 프롬프트에 다른 재지시 문구 추가
  - `tests/test_curator_agent.py` 6개 테스트 신규 (Mock 기반) — 전체 스위트 39/39 통과
- [ ] **T12 (~15min)** — RAGAS reason 필드 활성화 + 재시도 전략 분기
- [ ] **T13 (~15min)** — Curator 기반 RAG 필드 선택 (D15 룰 대체)
- [ ] **T14 (~20min)** — build_card() curator_instruction 파라미터 추가 (additive)
- [ ] **T15 (~20min)** — Phase 2 통합 테스트 (5개)
- [ ] **T16 (~15min)** — Phase 2 DB 마이그레이션

- [ ] **T17 (~15min)** — AgentHarness/LangSmith 통합 (Phase 1, generate_card 대상)
  - T3로 generate_card()가 Agent 분류 기준(GLOBAL_AGENT_RULE.md §1-2: Tool 2개 이상 선택 호출 + 품질평가·재시도 + 조건분기) 3/4 충족 → §7-2에 따라 AgentHarness 래핑 필요
  - shared.harness.AgentHarness로 generate_card() 호출 래핑, LANGCHAIN_PROJECT=module4-{githubId} 설정
  - TimeoutError는 async with 블록 바깥에서 처리 (§7-4 — 안에서 잡으면 status='success'로 잘못 기록됨)
  - 확인: LangSmith 대시보드에서 module4 프로젝트로 trace 기록 확인

---

## 13. 병렬 작업 순서

```
Lane A: DB 마이그레이션 (T1)                          — 단독 먼저
Lane B: pipeline/ (T2, T3, T6, T10)                  — Lane A 완료 후
Lane C: api/ + auth (T4, T5, T9)                     — Lane A 완료 후, Lane B와 병렬
Lane D: tests/ (T7)                                   — Lane B + C 완료 후

실행 순서: Lane A → [Lane B + Lane C 병렬] → Lane D
```

---

## 14. 실패 케이스 목록

| 코드경로 | 실패 시나리오 | 에러핸들링 | 비고 |
|---------|-------------|------------|------|
| embed_query() | Gemini API timeout | T6로 처리 | error_message 저장 |
| rag_search() | pgvector 결과 0개 | fallback | llm_fallback=True |
| ragas_eval() | 3회 모두 실패 | fallback_card() | llm_fallback=True |
| build_card() | gemini-2.5-flash API 오류 | T6 처리 완료 | generate_card() try/except → status='failed' + error_message |
| fallback_card() | gemini-2.5-pro API 오류 | T6 처리 완료 | 동일 try/except로 build_card()와 함께 wrap (마지막 안전망) |
| DB write | PostgreSQL 연결 끊김 | T6 처리 완료 | _run_card_generation() catch-all try/except → status='failed' + error_message |
| /api/learn 중복 | 동일 issue_id 재클릭 | D4 ON CONFLICT | 기존 plan 리다이렉트 |
| curator_agent() (Phase 2) | gemini-2.5-flash timeout | Phase 1 방식 fallback | — |
| Curator 재지시 루프 (Phase 2) | reason 무한 반복 | max 3 attempt 제한 | — |

---

## 15. 보안 리스크

| 리스크 | 심각도 | 해결책 |
|-------|--------|-------|
| user_id 평문 전송 | HIGH | GitHub OAuth (TODO-2) |
| POST /api/learn CSRF | MEDIUM | SameSite 쿠키 + CSRF 토큰 |
| LLM prompt injection (code_snippet) | MEDIUM | 길이 제한 + 시스템 프롬프트 분리 |
| Curator 출력 신뢰 (Phase 2) | MEDIUM | curator_instruction 필드별 길이/허용값 검증 |
| scan_id/plan_id 열거 공격 | LOW | UUID로 충분 |
| doc_chunk source_url XSS | LOW | 렌더링 시 이스케이프 (프론트 처리) |

---

## 16. Production 전 필수 TODO

| 항목 | 의존성 | 내용 |
|-----|--------|------|
| TODO-1: KMS 임베딩 확인 | T1 완료 후 | 직접 임베딩한 문서가 `chunk_embeddings`에 올바르게 저장됐는지, category 필터가 동작하는지 확인. `SELECT DISTINCT metadata->>'category' FROM chunk_embeddings;` |
| TODO-2: 코딩 에이전트 연동 | Phase 2 진입 시 | `POST /api/ingest` 실제 코딩 에이전트와 연결. Section 19 연동 경로 참조 |
| TODO-3: Curator 에이전트 | T10 완료 후 | T11~T16 진입점 |
| TODO-4: KMS 검색 백엔드 평가 | TODO-1 완료 후 | pgvector vs FTS vs Hybrid — SearchAdapter(D33) 기반 교체 |
| TODO-5: m0 KMS 시스템 연동 | m0 안정화 후 | 현재 직접 임베딩 → m0 파이프라인으로 교체. Section 19 연동 경로 참조 |

---

## 17. Additive 확장 보장 (Phase 1 → Phase 2 재작성 없음)

| Phase 1 코드 | Phase 2 변환 | 방식 |
|-------------|-------------|------|
| `ragas_eval() → reason=None` | `reason="low_faithfulness"\|"low_relevancy"` | 값 채우기 |
| `build_card(query, depth)` | `build_card(query, curator_instruction=ci)` | 파라미터 추가 |
| `issue.category → card_type` | `curator.card_type` | 조건문 제거 + Curator 추가 |
| `mistake_count >= 7 → depth` | `curator.depth` | 조건문 제거 + Curator 추가 |
| `rag_search(fixed_fields)` | `rag_search(curator.query_fields)` | 룰 제거 + Curator 추가 |

---

## 18. 성능 병목

```
Phase 1:
  RAGAS 1회 = gemini-2.5-pro 2-3회 호출 ≈ 2-4초
  3회 실패 시 최대 12초 + fallback 1초 = 최대 13초
  → 비동기 + polling으로 해결 (D2)

  pgvector 인덱스 없으면 O(n) 스캔
  → HNSW 인덱스로 해결 (D9, T1)

  BackgroundTasks 싱글 워커 병렬 한계
  → Phase 2에서 Celery 도입 예정

Phase 2 추가 비용:
  Curator (gemini-2.5-flash): 카드당 +$0.0001 수준 (허용 범위)
  전체 카드 3개: ~$0.0003 추가
```

---

## 19. 타 모듈 연동 경로

### 19-1. 현재 상태 (Phase 1 개발 시점)

| 데이터 | 현재 접근 방법 | 나중에 연결할 방법 |
|--------|-------------|----------------|
| `pull_requests` | **실 DB 직접 조회** — 공유 PostgreSQL, api-core alembic으로 이미 생성됨 | 변경 없음 |
| `users.user_id` | **JWT sub → users 테이블 조회** — 실 DB 사용 가능 | 변경 없음 |
| 코딩 에이전트 인풋 (`review_issue`) | **Cloud SQL 직접 INSERT** — Cloud SQL Studio에서 테스트 데이터 직접 삽입 (D34) | `POST /api/ingest` 실제 코딩 에이전트 연결 (TODO-2) |
| KMS 문서 (`chunk_embeddings`) | **직접 임베딩** — `scripts/embed_kms_docs.py`로 m4가 직접 문서 임베딩 | m0 KMS 파이프라인 안정화 후 교체 (TODO-5) |

### 19-2. 테스트 데이터 — 코딩 에이전트 인풋 (Cloud SQL 직접 INSERT)

```sql
-- Cloud SQL Studio에서 실행
-- pull_request_id, user_id는 실제 값으로 교체 필요
INSERT INTO review_issue (
    pull_request_id, user_id, github_id, agent,
    severity, keyword, sub_category, code_context,
    code_snippet, suggestion, programming_language,
    framework, framework_version, name_of_function
) VALUES (
    '04ad1ffc-d3f8-4576-b0aa-5f...',  -- pull_requests 테이블에서 조회
    'c4cdf4aa-9e02-408e-b990-e...',   -- users 테이블에서 조회
    'test-dev', 'security_scan',
    'critical', 'SQL Injection', 'input validation',
    '상품 검색 기능 — 사용자 입력을 쿼리에 직접 삽입',
    'def search(kw):\n    return db.execute(f''SELECT * FROM products WHERE name={kw}'')',
    'Parameterized Query 사용',
    'Python', 'FastAPI', '0.104.0', 'search_products'
);
```

---

### 19-3. KMS 직접 임베딩 — m0 연동 전 임시 방법

**지금 당장 사용하는 방법 (m0 없이):**

```python
# scripts/embed_kms_docs.py
# m0 KMS 시스템을 거치지 않고 직접 chunk_embeddings에 문서 삽입

import asyncpg
import os

# 사용할 임베딩 모델 (.env EMBEDDING_PROVIDER 기준)
# Ollama: EMBEDDING_PROVIDER=ollama, OLLAMA_EMBEDDING_MODEL=bge-m3 (1024차원)
# Gemini: google-generativeai text-multilingual-embedding-002
# → 반드시 기존 chunk_embeddings.embedding 차원과 동일해야 함

SAMPLE_DOCS = [
    {
        "content": "SQL Injection 방지를 위해 항상 Parameterized Query를 사용한다.",
        "metadata": {"category": "보안", "source": "m4-direct-embed"},
    },
    {
        "content": "FastAPI에서 SQLAlchemy를 이용한 안전한 쿼리 작성: session.execute(select(User).where(User.id == user_id))",
        "metadata": {"category": "코딩컨벤션", "source": "m4-direct-embed"},
    },
    # ... 추가 문서
]

async def embed_and_insert(docs: list[dict]):
    """문서 임베딩 후 chunk_embeddings에 직접 삽입."""
    conn = await asyncpg.connect(os.environ["POSTGRES_URL"])
    for doc in docs:
        vector = await get_embedding(doc["content"])  # 임베딩 함수 (모델에 맞게 구현)
        chunk_id = str(uuid.uuid4())
        # 먼저 chunks 테이블에 삽입 (FK 제약)
        await conn.execute("""
            INSERT INTO chunks (chunk_id, doc_id, chunk_type, content, trace_id)
            VALUES ($1, $2, 'child', $3, 'm4-seed')
        """, chunk_id, "00000000-0000-0000-0000-000000000001", doc["content"])
        # chunk_embeddings에 벡터 + metadata 삽입
        await conn.execute("""
            INSERT INTO chunk_embeddings (chunk_id, embedding, model_name, content, metadata)
            VALUES ($1, $2::vector, $3, $4, $5)
        """, chunk_id, vector, "bge-m3", doc["content"], json.dumps(doc["metadata"]))
    await conn.close()

# 실행: python scripts/embed_kms_docs.py
```

> **주의**: 위 스크립트는 `documents` 테이블 FK를 위해 더미 doc_id가 필요.  
> 또는 `documents` 테이블에 먼저 더미 행을 삽입한 후 chunks → chunk_embeddings 순서로 진행.

---

### 19-4. m0 KMS 연동 — 나중에 연결하는 방법

m0가 안정화되면 `embed_kms_docs.py`의 직접 임베딩을 m0 파이프라인으로 교체한다.

```
현재 방법 (m0 없이):
  m4 직접 임베딩 → chunk_embeddings 테이블 직접 삽입

m0 연동 후 방법:
  1. m0 POST /ingest 또는 문서 업로드 UI → m0가 청킹 + 임베딩 → chunk_embeddings 저장
  2. m4 rag_search()는 chunk_embeddings만 조회 → 코드 변경 없음
  3. metadata category 값이 m0가 임베딩할 때 설정한 값과 일치하는지 확인

연동 체크리스트:
  □ m0가 chunk_embeddings.metadata에 'category' 키를 저장하는지 확인
  □ category 값이 '보안', '코딩컨벤션', '코드성능검증'와 일치하는지 확인
  □ 임베딩 차원(vector 컬럼 길이)이 동일한지 확인
  □ embed_kms_docs.py로 삽입한 더미 데이터 정리
```

---

### 19-5. 코딩 에이전트 연동 — 나중에 연결하는 방법

```
현재 방법 (Cloud SQL 직접 INSERT):
  Cloud SQL Studio에서 review_issue 테이블에 테스트 데이터 직접 INSERT
  → 실제 pull_request_id, user_id 사용 (pull_requests 테이블 조회 후 입력)

코딩 에이전트 연동 후 방법:
  1. 코딩 에이전트가 PR 분석 완료 시 POST /api/ingest 호출
  2. m4가 review_issue 테이블에 저장
  3. DB에서 실제 이슈 조회 (기존 코드 그대로)

POST /api/ingest 연동 체크리스트:
  □ 코딩 에이전트가 보내는 JSON 스키마와 Section 4 스키마 일치 확인
  □ review_issue.severity 값 확인 ('critical'/'high'/'medium'/'low')
  □ JWT Bearer 토큰 또는 내부 서비스 토큰 인증 방식 확인
```

---

## 20. Cloud SQL 테이블 목록 (전체)

### 기존 테이블 (m4에서 읽기만)
| 테이블 | 관리 모듈 | m4 사용 방식 |
|--------|----------|-------------|
| `pull_requests` | api-core | 최신 PR 조회 (read-only) |
| `users` | api-core | user_id 확인 (read-only) |
| `chunk_embeddings` | m0/m4-seed | RAG 검색 (read-only) |

### T1에서 생성한 테이블 (m4 소유)
| 테이블 | 용도 |
|--------|------|
| `review_issue` | 코딩 에이전트 인풋 저장. 현재는 Cloud SQL Studio에서 직접 INSERT |
| `curriculum_plan` | 에이전트 실행 결과(학습 카드) 저장. card_content JSONB에 카드 전체 저장 |

### 추가 생성 필요한 테이블 (Section 12 T1-2로 마이그레이션)

#### `ragas_eval_log` — RAGAS 평가 결과 로그
```sql
CREATE TABLE ragas_eval_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id UUID NOT NULL REFERENCES curriculum_plan(id) ON DELETE CASCADE,
    attempt_number INTEGER NOT NULL,          -- 1, 2, 3차 시도
    faithfulness FLOAT,                       -- RAGAS faithfulness 점수
    answer_relevancy FLOAT,                   -- RAGAS answer_relevancy 점수
    passed BOOLEAN NOT NULL,                  -- 임계값(0.7) 통과 여부
    reason TEXT,                              -- Phase 2: "low_faithfulness" | "low_relevancy"
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```
> 용도: 추후 RAGAS 성능 비교, 임계값 튜닝, fallback 발생 빈도 분석

#### `kms_search_log` — RAG 검색 쿼리 로그
```sql
CREATE TABLE kms_search_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id UUID NOT NULL REFERENCES curriculum_plan(id) ON DELETE CASCADE,
    search_type INTEGER NOT NULL,             -- 1, 2, 3 (검색 종류)
    query_text TEXT NOT NULL,                 -- embed_query()에 전달된 쿼리 문자열
    category TEXT NOT NULL,                   -- 보안 | 코딩컨벤션 | 코드성능검증
    result_count INTEGER NOT NULL,            -- 반환된 청크 수
    top_similarity FLOAT,                     -- 상위 1개 유사도 점수
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```
> 용도: TODO-4 RAG 백엔드 성능 비교(pgvector vs FTS vs Hybrid), 검색 품질 모니터링
