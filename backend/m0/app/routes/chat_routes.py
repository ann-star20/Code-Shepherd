"""
KMS 사내 지식 챗봇 — RAG 파이프라인 (SQLAlchemy async 버전)

POST /chat : question 임베딩 → Intent 분류 → 멀티 스토리지 쿼리 → LLM 답변 생성

환경변수:
    OLLAMA_BASE_URL        (기본값: http://localhost:11434)
    OLLAMA_EMBEDDING_MODEL (기본값: bge-m3)
    GOOGLE_API_KEY         (필수 — 운영 환경)
    CHAT_LLM_MODEL         (기본값: gemini-2.5-flash)
    USE_MOCK_LLM           (기본값: true — Mock LLM 사용)
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from dataclasses import dataclass, field

import httpx
from fastapi import APIRouter
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

_OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "bge-m3")
_LLM_MODEL = os.getenv("CHAT_LLM_MODEL", "gemini-2.5-flash")
_USE_MOCK_LLM = os.getenv("USE_MOCK_LLM", "true").lower() == "true"

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat"])

# lifespan에서 주입
_db_session_factory: async_sessionmaker[AsyncSession] | None = None
_storage = None


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _db_session_factory is None:
        raise RuntimeError("DB session factory가 초기화되지 않았습니다. lifespan을 확인하세요.")
    return _db_session_factory


def _get_storage():
    if _storage is None:
        from app.storage import get_storage
        return get_storage()
    return _storage


# ---------------------------------------------------------------------------
# 요청/응답 모델
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    question: str
    top_k: int = 5

    @field_validator("question")
    @classmethod
    def question_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("질문이 비어있습니다.")
        return v


class ChatSource(BaseModel):
    chunk_id: str
    content: str
    score: float
    doc_title: str | None = None
    source_type: str = "pgvector"
    page_image_path: str | None = None


class ChatResponse(BaseModel):
    question: str
    answer: str
    sources: list[ChatSource]
    model: str
    intent: str = "semantic"
    storages: list[str] = ["pgvector"]


# ---------------------------------------------------------------------------
# Intent Classification
# ---------------------------------------------------------------------------

@dataclass
class IntentResult:
    intent: str
    storages: list[str] = field(default_factory=list)
    query_hint: str = ""


_INTENT_SYSTEM_PROMPT = """\
당신은 사내 지식 검색 시스템의 쿼리 라우터입니다.
사용자 질문을 분석해 아래 JSON 형식으로만 응답하세요. 다른 텍스트 금지.

intent 선택 기준:
- semantic:    의미 검색 ("설명해줘", "방법", "가이드", "어떻게")
- structured:  통계/목록 ("몇 개", "목록", "최근", "어떤 파일")
- graph:       관계/연결 ("관련된", "연관", "연결", "개념들")
- file:        파일 직접 조회 ("파일 내용", "원본", "보여줘" + 파일명)

storages: intent에 맞는 DB 목록 (pgvector/postgresql/neo4j/gcs)

{"intent":"<intent>","storages":["<db>"],"query_hint":"<SQL 힌트 또는 키워드>"}"""

_INTENT_MOCK = IntentResult(intent="semantic", storages=["pgvector"], query_hint="")


async def call_gemini_with_retry(messages):  # type: ignore[empty-body]
    """Gemini 호출 — 테스트에서 monkeypatch 대상."""
    from langchain_google_genai import ChatGoogleGenerativeAI
    llm = ChatGoogleGenerativeAI(
        model=_LLM_MODEL,
        temperature=0,
        google_api_key=os.getenv("GOOGLE_API_KEY"),
    )
    return await llm.ainvoke(messages)


async def _classify_intent(question: str) -> IntentResult:
    """Gemini로 질문의 intent와 대상 Storage를 분류한다."""
    if _USE_MOCK_LLM:
        return _INTENT_MOCK

    from langchain_core.messages import HumanMessage, SystemMessage
    try:
        response = await call_gemini_with_retry([
            SystemMessage(content=_INTENT_SYSTEM_PROMPT),
            HumanMessage(content=question),
        ])
        raw = response.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()
        data = json.loads(raw)
        return IntentResult(
            intent=data.get("intent", "semantic"),
            storages=data.get("storages", ["pgvector"]),
            query_hint=data.get("query_hint", ""),
        )
    except Exception:
        logger.warning("Intent 분류 실패 — semantic으로 폴백")
        return IntentResult(intent="semantic", storages=["pgvector"], query_hint="")


# ---------------------------------------------------------------------------
# SQL 보안 검증
# ---------------------------------------------------------------------------

_SQL_ALLOWED_TABLES = frozenset({"documents", "chunks", "agent_traces"})


def _validate_sql_v2(sql: str) -> bool:
    """sqlglot AST 기반 SQL 검증 — UNION/stacked query/unauthorized table 차단.

    허용 조건:
    - 단일 SELECT 문 (세미콜론 stacked query 차단)
    - LIMIT 필수
    - 접근 테이블이 _SQL_ALLOWED_TABLES 안에만 있어야 함
    - UNION 차단 (Union 노드는 Select가 아님 → isinstance 검사로 자동 차단)
    """
    import sqlglot
    from sqlglot import exp

    sql = sql.strip()
    if not sql:
        return False

    try:
        statements = sqlglot.parse(sql, dialect="postgres")
    except sqlglot.errors.SqlglotError:
        # ParseError + TokenError 등 sqlglot 계열 예외 모두 차단
        return False

    if len(statements) != 1:
        return False

    stmt = statements[0]
    if stmt is None:
        return False

    if not isinstance(stmt, exp.Select):
        return False

    # data-modifying 노드 차단 — CTE 이름을 허용 테이블명으로 위장한
    # WITH x AS (DELETE/UPDATE/INSERT ...) SELECT ... 우회 방어
    if next(stmt.find_all(exp.Insert, exp.Update, exp.Delete), None) is not None:
        return False

    if stmt.args.get("limit") is None:
        return False

    tables = list(stmt.find_all(exp.Table))
    if not tables:
        return False

    for table in tables:
        if table.name.lower() not in _SQL_ALLOWED_TABLES:
            return False

    return True


# ---------------------------------------------------------------------------
# 스토리지별 쿼리 헬퍼
# ---------------------------------------------------------------------------

async def _query_pgvector(
    question: str,
    session_factory: async_sessionmaker[AsyncSession],
    top_k: int = 5,
) -> list[dict]:
    """질문을 임베딩해 chunk_embeddings에서 코사인 유사도 상위 k개를 반환한다.

    chunk_embeddings에 저장된 model_name을 확인해 쿼리 임베딩 모델을 맞춘다.
    모델이 섞여 있으면 각 모델로 임베딩 후 UNION해서 top_k를 재정렬한다.
    """
    async with session_factory() as session:
        model_rows = await session.execute(
            text("SELECT DISTINCT model_name FROM chunk_embeddings WHERE model_name IS NOT NULL")
        )
        stored_models: list[str] = [r[0] for r in model_rows.fetchall()]

    if not stored_models:
        stored_models = [_EMBEDDING_MODEL]

    openai_model_prefix = "text-embedding"
    all_results: list[dict] = []

    for model_name in stored_models:
        if model_name.startswith(openai_model_prefix):
            embedding = await _embed_question_openai(question, model_name)
        else:
            embedding = await _embed_question_ollama(question, model_name)

        embedding_str = json.dumps(embedding)

        async with session_factory() as session:
            result = await session.execute(
                text("""
                    SELECT
                        chunk_id::text,
                        content,
                        1 - (embedding <=> CAST(:embedding AS vector)) AS score,
                        metadata->>'doc_title' AS doc_title,
                        metadata
                    FROM chunk_embeddings
                    WHERE model_name = :model_name
                    ORDER BY embedding <=> CAST(:embedding AS vector)
                    LIMIT :top_k
                """),
                {"embedding": embedding_str, "top_k": top_k, "model_name": model_name},
            )
            rows = result.mappings().fetchall()

        for r in rows:
            all_results.append({
                "chunk_id": r["chunk_id"],
                "content": r["content"],
                "score": float(r["score"]),
                "doc_title": r["doc_title"],
                "source_type": "pgvector",
                "metadata": r["metadata"] if isinstance(r.get("metadata"), dict) else {},
            })

    # 여러 모델이 섞인 경우 score 내림차순 재정렬 후 top_k 반환
    all_results.sort(key=lambda x: x["score"], reverse=True)
    return all_results[:top_k]


async def _embed_question_ollama(question: str, model: str | None = None) -> list[float]:
    """Ollama로 질문을 임베딩한다 (model 미지정 시 환경변수 기본값 사용)."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{_OLLAMA_BASE_URL}/api/embeddings",
            json={"model": model or _EMBEDDING_MODEL, "prompt": question},
        )
        response.raise_for_status()
        return response.json()["embedding"]


async def _embed_question_openai(question: str, model: str) -> list[float]:
    """OpenAI로 질문을 임베딩한다 (저장 시와 동일 dimensions 유지)."""
    from openai import AsyncOpenAI
    pgvector_dim = int(os.getenv("PGVECTOR_DIMENSION", "1024"))
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = await client.embeddings.create(
        model=model,
        input=question,
        dimensions=pgvector_dim,
    )
    return response.data[0].embedding


async def _embed_question(question: str) -> list[float]:
    """하위 호환용 래퍼 — bge-m3 기본값."""
    return await _embed_question_ollama(question)


_POSTGRESQL_SCHEMA_HINT = """\
테이블: documents (doc_id UUID, title TEXT, file_type TEXT, upload_status TEXT, created_at TIMESTAMP)
테이블: chunks (chunk_id UUID, doc_id UUID, content TEXT, chunk_type TEXT)
테이블: chunk_embeddings (chunk_id UUID, content TEXT, metadata JSONB)"""

_TEXT_TO_SQL_SYSTEM_PROMPT = """\
당신은 PostgreSQL 전문가입니다.
사용자 질문을 아래 스키마 기반으로 SELECT 쿼리 하나로만 변환하세요.
LIMIT를 반드시 포함하고, SELECT 이외의 명령(INSERT/UPDATE/DELETE/DROP 등)은 절대 사용하지 마세요.
쿼리만 출력하고 다른 텍스트는 출력하지 마세요.

{schema}"""


async def _generate_sql(question: str, schema_hint: str = "") -> str:
    """Gemini로 자연어 질문을 PostgreSQL SELECT 쿼리로 변환한다."""
    if _USE_MOCK_LLM:
        return "SELECT title, file_type, upload_status FROM documents LIMIT 10"

    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_core.messages import HumanMessage, SystemMessage

    llm = ChatGoogleGenerativeAI(
        model=_LLM_MODEL,
        temperature=0,
        google_api_key=os.getenv("GOOGLE_API_KEY"),
    )
    schema = schema_hint or _POSTGRESQL_SCHEMA_HINT
    messages = [
        SystemMessage(content=_TEXT_TO_SQL_SYSTEM_PROMPT.format(schema=schema)),
        HumanMessage(content=question),
    ]
    try:
        response = await llm.ainvoke(messages)
        sql = response.content.strip()
        if sql.startswith("```"):
            sql = sql.split("```")[1].lstrip("sql").strip()
        return sql
    except Exception:
        logger.warning("Text-to-SQL 생성 실패 — 기본 쿼리 반환")
        return "SELECT title FROM documents LIMIT 5"


async def _query_postgresql(
    question: str,
    session_factory: async_sessionmaker[AsyncSession],
    schema_hint: str = "",
) -> list[dict]:
    """Text-to-SQL로 생성된 쿼리를 검증 후 PostgreSQL에서 실행한다."""
    sql = await _generate_sql(question, schema_hint)
    if not _validate_sql_v2(sql):
        logger.warning(f"_validate_sql_v2 실패 — 쿼리 차단: {sql[:80]}")
        return []

    async with session_factory() as session:
        result = await session.execute(text(sql))
        rows = result.mappings().fetchall()

    return [
        {**dict(row), "source_type": "postgresql"}
        for row in rows
    ]


_GCS_BUCKET = os.getenv("GCS_BUCKET", "tasklink-kms-storage-dev")


async def _fetch_gcs_markdown(file_name: str) -> str:
    """GCS에서 Markdown 파일을 읽어 문자열로 반환한다."""
    try:
        from google.cloud import storage as gcs_storage  # type: ignore
    except ImportError:
        logger.warning("google-cloud-storage 미설치 — GCS 조회 건너뜁니다.")
        return ""

    client = gcs_storage.Client()
    bucket = client.bucket(_GCS_BUCKET)
    blob = bucket.blob(file_name)
    return blob.download_as_text(encoding="utf-8")


async def _query_gcs(question: str) -> list[dict]:
    """질문에서 파일명을 추출해 GCS Markdown을 fetch하고 Gemini로 요약한다."""
    import re
    file_match = re.search(r"[\w가-힣]+\.md", question)
    file_name = file_match.group(0) if file_match else f"{question.split()[0]}.md"

    try:
        content = await _fetch_gcs_markdown(file_name)
    except Exception as e:
        logger.warning(f"GCS fetch 실패: {e}")
        return []

    if not content.strip():
        return []

    summary = await _generate_answer(question, content)
    return [
        {
            "chunk_id": file_name,
            "content": summary,
            "score": 1.0,
            "doc_title": file_name,
            "source_type": "gcs",
        }
    ]


_NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
_NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
_NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

_CYPHER_RELATED_ENTITIES = """\
MATCH (e:Entity)<-[:MENTIONS]-(c:Chunk)
WHERE toLower(e.name) CONTAINS toLower($keyword)
RETURN e.name AS entity, c.content AS chunk, 'MENTIONS' AS relation
LIMIT 10"""


async def _run_cypher(cypher: str, params: dict | None = None) -> list[dict]:
    """Neo4j 드라이버로 Cypher를 실행하고 결과를 dict 리스트로 반환한다."""
    try:
        from neo4j import AsyncGraphDatabase
    except ImportError:
        logger.warning("neo4j 패키지 미설치 — Neo4j 조회 건너뜁니다.")
        return []

    driver = AsyncGraphDatabase.driver(
        _NEO4J_URI, auth=(_NEO4J_USER, _NEO4J_PASSWORD)
    )
    try:
        async with driver.session() as neo4j_session:
            result = await neo4j_session.run(cypher, parameters=params or {})
            return [dict(record) async for record in result]
    finally:
        await driver.close()


async def _query_neo4j(question: str) -> list[dict]:
    """질문 키워드로 Neo4j Entity-Chunk 관계 그래프를 조회한다."""
    keyword = question.split()[0] if question.split() else question
    try:
        records = await _run_cypher(_CYPHER_RELATED_ENTITIES, {"keyword": keyword})
    except Exception as e:
        logger.warning(f"Neo4j 조회 실패: {e}")
        return []

    return [
        {**record, "source_type": "neo4j"}
        for record in records
    ]


# ---------------------------------------------------------------------------
# C-1: GCS 이미지 로더
# ---------------------------------------------------------------------------

async def _load_page_image(path: str | None) -> bytes | None:
    """GCS에서 page_image_path로 이미지 바이트 로드. 실패 시 None."""
    if not path:
        return None
    try:
        storage = _get_storage()
        return await storage.load(path)
    except Exception:
        logger.warning(f"페이지 이미지 로드 실패: {path}")
        return None


# ---------------------------------------------------------------------------
# C-2: 청크에서 이미지 수집 (중복 제거)
# ---------------------------------------------------------------------------

async def _collect_page_images(chunks: list[dict]) -> list[bytes]:
    """청크 목록에서 page_image_path를 수집해 중복 제거 후 이미지를 병렬 로드."""
    seen: set[str] = set()
    paths: list[str] = []
    for chunk in chunks:
        path = (chunk.get("metadata") or {}).get("page_image_path")
        if path and path not in seen:
            seen.add(path)
            paths.append(path)
    if not paths:
        return []
    results = await asyncio.gather(*[_load_page_image(p) for p in paths])
    return [img for img in results if img is not None]


# ---------------------------------------------------------------------------
# C-3: Gemini 멀티모달 답변 생성
# ---------------------------------------------------------------------------

async def _generate_answer(
    question: str,
    context: str,
    page_images: list[bytes] = [],
) -> str:
    """Gemini 2.5 Flash로 RAG 답변을 생성한다. USE_MOCK_LLM=true이면 Mock 반환."""
    if _USE_MOCK_LLM:
        if context.strip():
            return f"[Mock 답변] 질문 '{question}'에 대한 컨텍스트를 찾았습니다."
        return f"[Mock 답변] 질문 '{question}'에 대한 관련 정보를 찾지 못했습니다."

    from langchain_core.messages import HumanMessage, SystemMessage

    llm = ChatGoogleGenerativeAI(
        model=_LLM_MODEL,
        temperature=0,
        google_api_key=os.getenv("GOOGLE_API_KEY"),
    )
    system_prompt = (
        "당신은 사내 지식 베이스를 활용하는 AI 어시스턴트입니다. "
        "아래 제공된 컨텍스트를 바탕으로 질문에 한국어로 정확하게 답변하세요. "
        "컨텍스트에 없는 내용은 모른다고 말하세요."
    )
    text_part = (
        f"[컨텍스트]\n{context}\n\n[질문]\n{question}"
        if context.strip()
        else question
    )

    if page_images:
        # 멀티모달: 텍스트 + 이미지 파트를 리스트로 구성
        content_parts: list = [{"type": "text", "text": text_part}]
        for img_bytes in page_images:
            b64 = base64.b64encode(img_bytes).decode("utf-8")
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"},
            })
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=content_parts)]
    else:
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=text_part)]

    response = await llm.ainvoke(messages)
    return response.content


# ---------------------------------------------------------------------------
# 엔드포인트
# ---------------------------------------------------------------------------

@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    멀티 스토리지 RAG 챗봇 엔드포인트.

    1. Intent Classifier → intent / storages 결정
    2. storages에 따라 pgVector / PostgreSQL / Neo4j / GCS 쿼리
    3. 검색 결과를 컨텍스트로 LLM 답변 생성
    4. answer + sources + intent + storages 반환
    """
    session_factory = _get_session_factory()

    intent_result = await _classify_intent(request.question)
    storages = intent_result.storages or ["pgvector"]

    raw_chunks: list[dict] = []
    for storage in storages:
        if storage == "pgvector":
            results = await _query_pgvector(request.question, session_factory, top_k=request.top_k)
        elif storage == "postgresql":
            results = await _query_postgresql(request.question, session_factory)
        elif storage == "neo4j":
            results = await _query_neo4j(request.question)
        elif storage == "gcs":
            results = await _query_gcs(request.question)
        else:
            results = await _query_pgvector(request.question, session_factory, top_k=request.top_k)
        raw_chunks.extend(results)

    context = "\n\n".join(
        f"[{c.get('doc_title') or '출처 미상'}]\n{c.get('content', '')}"
        for c in raw_chunks
    )
    page_images = await _collect_page_images(raw_chunks)
    answer = await _generate_answer(request.question, context, page_images=page_images)

    sources = [
        ChatSource(
            chunk_id=c.get("chunk_id", ""),
            content=c.get("content", ""),
            score=float(c.get("score", 0.0)),
            doc_title=c.get("doc_title"),
            source_type=c.get("source_type", "pgvector"),
            page_image_path=(c.get("metadata") or {}).get("page_image_path"),
        )
        for c in raw_chunks
    ]

    return ChatResponse(
        question=request.question,
        answer=answer,
        sources=sources,
        model=_LLM_MODEL,
        intent=intent_result.intent,
        storages=storages,
    )
