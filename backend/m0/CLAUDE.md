# Module 0 (m0) — KMS 사내 지식 파이프라인 세부 구현 지침

**담당**: Dev1  
**위치**: `backend/m0/`  
**패키지 관리**: `uv` (`pyproject.toml`)  
**DB 레이어**: SQLAlchemy async (`async_sessionmaker[AsyncSession]`)

> 팀 전역 규칙은 루트 `CLAUDE.md` 참조.  
> Agent/Tool/Harness/State 규칙은 `docs/GLOBAL_AGENT_RULE.md` 참조.

---

## 1. Stage별 처리 흐름

```
문서 업로드 (PDF/DOCX/PPTX/TXT/MD)
    │
    ▼ Stage 1: DocumentParserAgent          [app/pipeline/stage1_document_parser_agent.py]
    │   Upstage API (HIGH complexity PDF) → Gemini Multimodal 폴백
    │
    ▼ Stage 2: MarkdownValidateAgent        [app/pipeline/stage2_validate_agent.py]  ← Agent (retry loop)
    │   quality_score >= 0.8 목표
    │   _apply_targeted_fix(): table_loss → post_process / heading → normalize / 기타 → gemini
    │   STAGE2_MAX_FIX_ATTEMPTS=2 (env 조정 가능)
    │
    ▼ Stage 3: ChunkingTool                 [app/pipeline/stage3_chunk.py]           ← Tool (결정론적)
    │   512토큰 / overlap 128 / Parent-Child 구조
    │
    ▼ Stage 4: ChunkValidateTool            [app/pipeline/stage4_chunk_validate.py]  ← Tool (규칙 기반)
    │   100~1500 토큰 범위 검증 / Parent-Child 연결 확인
    │
    ▼ Stage 5: MetadataExtractAgent         [app/pipeline/stage5_metadata_agent.py]  ← LLM
    │   Stage 5b: MetadataValidateAgent     [app/pipeline/stage5b_metadata_validate_agent.py]
    │   카테고리/태그/엔티티 추출 + 검증
    │
    ▼ Stage 6: StoreRouteTool               [app/pipeline/stage6_store.py]           ← Tool
        pgVector + PostgreSQL + GCS + Neo4j (실패 시 stored_partial)
```

---

## 2. Stage별 Trace ID 체계

```
trc_0001_{doc_id_8hex}   Stage 1: Markdown 변환
trc_0002_{doc_id_8hex}   Stage 2: Markdown 검증
trc_0003_{doc_id_8hex}   Stage 3: 청킹
trc_0004_{doc_id_8hex}   Stage 4: Chunk 검증
trc_0005_{doc_id_8hex}   Stage 5: 메타데이터 추출
trc_0005b_{doc_id_8hex}  Stage 5b: 메타데이터 검증
trc_0006_{doc_id_8hex}   Stage 6: 저장 & 라우팅

예시: trc_0001_3a9f1c2b
```

> ⚠️ `new_pipeline_trace(stage)` 호출 시 반드시 `doc_id` 전달.  
> 없으면 trc_0001 고정값 → 두 번째 문서 처리 시 첫 번째 기록 덮어씀.

```python
from shared.trace import DocPipelineStage, new_pipeline_trace
from shared.harness import AgentHarness

trace_id = new_pipeline_trace(DocPipelineStage.MARKDOWN_CONVERT, doc_id=doc_id)

try:
    async with AgentHarness(
        trace_id=trace_id,
        agent_name="DocumentParserAgent",
        db_session_factory=session_factory,   # asyncpg.Pool 아님!
        doc_id=doc_id,
    ) as harness:
        result = await harness.run(graph.ainvoke, state)
except asyncio.TimeoutError:
    return make_timeout_result("DocumentParserAgent")
```

---

## 3. HITL 발동 조건 (KMS 전용)

| 조건 | 임계값 | 처리 |
|------|--------|------|
| Markdown 품질 점수 | < 0.8 | HITL 큐 등록, Stage 2 중단 |
| 표/이미지 구조 손실 | 발생 시 | HITL 큐 등록 |
| Chunk 길이 기준 초과/미달 | 발생 시 | HITL 큐 등록 |
| Parent-Child 연결 실패 | 발생 시 | HITL 큐 등록 |

```python
from shared.config import get_settings

settings = get_settings()

if score < settings.markdown_quality_threshold:   # 0.8 기본값
    await hitl_queue.enqueue({
        "doc_id": doc_id,
        "reason": issues,
        "quality_score": score,
        "agent_name": "MarkdownValidateAgent",
        "stage": "stage2_validate",
    })
    return {"status": "hitl_pending", "validated_markdown": None}
```

---

## 4. SQL 방어 규칙 (Chat API)

Chat API에서 LLM이 생성한 SQL을 실행하기 전 반드시 검증한다.

```python
_SQL_ALLOWED_TABLES = frozenset({"documents", "chunks", "agent_traces"})

def _validate_sql_v2(sql: str) -> bool:
    """sqlglot AST 기반 SQL 검증 — UNION/stacked query/unauthorized table 차단."""
    import sqlglot
    from sqlglot import exp
    # 1. Parse 실패 → False
    # 2. 복수 statements → False (stacked query 차단)
    # 3. SELECT 외 → False
    # 4. LIMIT 없음 → False
    # 5. 허용 테이블 외 접근 → False
```

---

## 5. 임베딩 모델

```
모델: Ollama bge-m3 (1024차원, 한국어 포함 다국어)
설정: PGVECTOR_DIMENSION=1024  ← shared/config.py Settings.pgvector_dimension

아래 세 곳이 반드시 일치해야 한다 — 하나라도 다르면 첫 번째 INSERT에서 오류:
  - shared/config.py: pgvector_dimension = Field(default=1024)
  - alembic 마이그레이션 DDL: vector(1024)
  - stage6_store.py: PGVECTOR_DIMENSION 상수
```

---

## 6. DB 레이어 규칙 (팀 전용 — asyncpg 직접 사용 금지)

이 모듈은 SQLAlchemy async를 사용한다. asyncpg Pool을 직접 사용하지 않는다.

```python
# ✅ 올바른 패턴
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy import text

async def _save_document(session: AsyncSession, ...) -> None:
    await session.execute(
        text("INSERT INTO documents (...) VALUES (:doc_id, ...)"),
        {"doc_id": str(doc_id), ...},
    )

async def stage6_store(state, db_session_factory: async_sessionmaker[AsyncSession], storage):
    async with db_session_factory() as session:
        async with session.begin():
            await _save_document(session, ...)

# ❌ 금지 패턴
async with db_pool.acquire() as conn:         # asyncpg Pool — 사용 금지
    await conn.execute("... $1 $2 ...", v1, v2)  # $N 포지셔널 파라미터 — 금지
```

---

## 7. API 엔드포인트 (m0 전용)

| 엔드포인트 | 파일 | 설명 |
|-----------|------|------|
| `POST /ingest` | app/main.py | 문서 업로드 + 파이프라인 시작 |
| `GET /health` | app/main.py | 헬스체크 |
| `GET /kms/status/{doc_id}` | app/routes/*.py | 파이프라인 진행 상태 폴링 |
| `GET /kms/docs/{id}/details` | app/routes/*.py | 파싱 상세 (quality_score 등) |
| `GET /kms/search` | app/routes/*.py | pgVector 유사도 검색 |
| `GET /hitl/queue` | app/routes/*.py | HITL 큐 목록 |
| `POST /hitl/queue/{id}/approve` | app/routes/*.py | HITL 승인 |
| `POST /hitl/queue/{id}/suggest-category` | app/routes/*.py | KB Evolution AI 제안 |
| `POST /chat` | app/routes/*.py | 멀티 스토리지 RAG 챗봇 |

> 현재 구현된 라우트는 `app/main.py`의 `/ingest`와 `/health` 두 개.  
> 나머지는 `app/routes/` 폴더를 만들고 추가 구현 예정.

---

## 8. 테스트 실행

```bash
# uv 환경에서 실행 (backend/m0/ 기준)
cd backend/m0
uv run pytest tests/ -v

# 특정 모듈
uv run pytest tests/test_contract.py -v          # Output Contract 검증
```

**주의사항**:
- 실제 DB/LLM 없이 Mock 기반으로 작성한다 (섹션 13 — 팀 전역 CLAUDE.md 참조)
- `stage1_document_parser_agent` 테스트는 Upstage/Gemini API를 직접 호출하므로 통합 테스트 주간(Week 5)까지 mock 처리

---

## 9. 환경변수 (m0 전용)

> **실제 값은 `.env` 파일에만 저장한다. 이 파일에 API key, 비밀번호를 절대 적지 않는다.**  
> 모든 설정은 `shared/config.py`의 `get_settings()`로 접근한다.

```bash
# Upstage (PDF 파싱)
UPSTAGE_API_KEY=                  # .env에서 설정 (HIGH complexity PDF)
UPSTAGE_DAILY_LIMIT=100           # 일일 호출 한도

# Gemini (멀티모달 폴백 + 품질 개선)
GOOGLE_API_KEY=                   # .env에서 설정
GEMINI_MODEL=gemini-2.5-flash

# KMS 파이프라인 임계값
MARKDOWN_QUALITY_THRESHOLD=0.8
STAGE2_MAX_FIX_ATTEMPTS=2
GEMINI_FALLBACK_IMAGE_RATIO=0.3
LARGE_DOC_CHUNK_THRESHOLD=50      # 이 이상이면 OpenAI 임베딩 폴백

# 임베딩
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_EMBEDDING_MODEL=bge-m3
PGVECTOR_DIMENSION=1024

# 저장소
STORAGE_BACKEND=gcs               # gcs | local
GCS_BUCKET=                       # .env에서 설정
GCS_PROJECT=                      # .env에서 설정

# LangSmith (GitHub ID로 교체 필수)
LANGCHAIN_PROJECT=module0-yourGitHubId
```

---

## 10. 구현 파일 위치 (m0 기준)

```
backend/m0/
├── app/
│   ├── main.py                              # ✅ FastAPI 진입점 (lifespan + 라우터 등록)
│   ├── models.py                            # SQLAlchemy ORM (documents, chunks, chunk_embeddings, agent_traces)
│   ├── storage.py                           # ✅ Storage 추상 레이어 (LocalStorage / GCSStorage)
│   ├── categories_db.py                     # ✅ categories 테이블 CRUD (SQLAlchemy async)
│   ├── routes/
│   │   ├── kms_routes.py                    # ✅ /kms/* 엔드포인트 (upload/status/search/docs/stats)
│   │   ├── hitl_routes.py                   # ✅ /hitl/* 엔드포인트 (queue/approve/reject/reprocess)
│   │   └── chat_routes.py                   # ✅ /chat 멀티 스토리지 RAG 챗봇
│   └── pipeline/
│       ├── models.py                        # ✅ DocPipelineState TypedDict + make_reprocess_state()
│       ├── graph.py                         # ✅ LangGraph StateGraph (7단계, HITL 분기)
│       ├── stage6_store.py                  # ✅ 구현 완료 (SQLAlchemy async)
│       ├── _gemini.py                       # ✅ Gemini 싱글턴 + tenacity 재시도 래퍼
│       ├── _category_definitions.py         # ✅ 카테고리 정의 공통 모듈
│       ├── stage1_document_parser_agent.py  # ✅ A-2: _parse_with_quality_loop + Upstage/PyMuPDF/Gemini
│       ├── stage2_validate_agent.py         # ✅ A-1: _select_fix_tool_with_llm LLM 도구 선택
│       ├── stage3_chunk.py                  # ✅ Parent-Child 청킹 (tiktoken 싱글턴)
│       ├── stage4_chunk_validate.py         # ✅ 청크 검증 + HITL 트리거
│       ├── stage5_metadata_agent.py         # ✅ 메타데이터 + Neo4j 엔티티 추출
│       └── stage5b_metadata_validate_agent.py # ✅ 메타데이터 검증 + KB Evolution HITL
├── alembic/
│   └── env.py                               # ✅ app.models import 추가 완료
├── tests/
│   └── test_contract.py                     # Output Contract 검증
└── pyproject.toml                           # ✅ KMS 의존성 추가 완료

backend/_shared/shared/
├── harness.py                               # ✅ SQLAlchemy async 버전 이관 완료
├── trace.py                                 # ✅ DocPipelineStage enum 이관 완료
├── config.py                                # ✅ KMS 설정 필드 추가 완료
└── db.py                                    # SQLAlchemy engine + async_sessionmaker
```

---

## 11. 참고 — 개인 프로젝트와의 차이

개인 프로젝트 (`D:\3차 프로젝트_아키텍쳐\src\kms\`)에서 이관 시 주의할 점:

| 항목 | 개인 프로젝트 | 팀 프로젝트 (m0) |
|------|------------|-----------------|
| DB 연결 | `asyncpg.Pool` | `async_sessionmaker[AsyncSession]` |
| SQL 파라미터 | `$1, $2` (positional) | `:param` (named) |
| executemany | `conn.executemany(q, list_of_tuples)` | `session.execute(text(q), list_of_dicts)` |
| 트랜잭션 | `async with conn.transaction()` | `async with session.begin()` |
| 설정 로드 | `os.getenv("KEY")` | `get_settings().key` |
| 패키지 관리 | pip / conda | uv (`pyproject.toml`) |
| 테스트 환경 | anaconda myenv11 | `uv run pytest` |
