"""Stage 6: 저장 & 라우팅 (trc_0006).

저장 대상:
    PostgreSQL  documents, chunks 테이블
    pgVector    chunk_embeddings (Ollama bge-m3 1024차원 / OpenAI 대용량 폴백)
    GCS / Local 원본 파일, Markdown 파일
    Neo4j       Document 노드, Chunk 노드, Entity 노드, MENTIONS 관계

Neo4j 연결 실패는 경고만 남기고 파이프라인을 계속 진행한다.

출력:
    state["stored"]        True
    state["storage_paths"] {"original": ..., "markdown": ...}
    state["status"]        "stored" | "stored_partial"
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import TYPE_CHECKING
from uuid import UUID

import aiofiles
import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

try:
    from neo4j import AsyncGraphDatabase
except ImportError:
    AsyncGraphDatabase = None  # type: ignore[assignment,misc]

if TYPE_CHECKING:
    from app.pipeline.models import DocPipelineState
    from app.storage import Storage

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "bge-m3")
PGVECTOR_DIMENSION = int(os.getenv("PGVECTOR_DIMENSION", "1024"))
LARGE_DOC_CHUNK_THRESHOLD = int(os.getenv("LARGE_DOC_CHUNK_THRESHOLD", "50"))
OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"

# Ollama 동시 요청 제한 (단일 프로세스 — 메모리 과부하 방지)
_EMBED_SEM = asyncio.Semaphore(5)
_OPENAI_SEM = asyncio.Semaphore(20)

# ---------------------------------------------------------------------------
# Neo4j 드라이버 싱글턴
# ---------------------------------------------------------------------------

_neo4j_driver = None


def _get_neo4j_driver():
    global _neo4j_driver
    if _neo4j_driver is None:
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "password")
        _neo4j_driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    return _neo4j_driver


# ---------------------------------------------------------------------------
# 임베딩 생성
# ---------------------------------------------------------------------------

async def _embed_text(text_: str) -> list[float]:
    """Ollama bge-m3로 텍스트 임베딩 생성 (동시 요청 5개 제한)."""
    async with _EMBED_SEM:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/embeddings",
                json={"model": EMBEDDING_MODEL, "prompt": text_},
            )
            response.raise_for_status()
            return response.json()["embedding"]


async def _embed_text_openai(text_: str) -> list[float]:
    """OpenAI text-embedding-3-small로 임베딩 생성.

    dimensions=1024 지정으로 bge-m3와 동일 차원 유지 → pgVector 스키마 변경 불필요.
    대용량 문서(child chunk > LARGE_DOC_CHUNK_THRESHOLD)에서 자동 사용.
    """
    from openai import AsyncOpenAI
    async with _OPENAI_SEM:
        client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = await client.embeddings.create(
            model=OPENAI_EMBEDDING_MODEL,
            input=text_,
            dimensions=PGVECTOR_DIMENSION,
        )
        return response.data[0].embedding


def _select_embed_fn(child_chunk_count: int):
    """child chunk 수와 API KEY 유무에 따라 임베딩 함수를 선택한다."""
    openai_key = os.getenv("OPENAI_API_KEY", "")
    if (
        child_chunk_count > LARGE_DOC_CHUNK_THRESHOLD
        and openai_key
        and openai_key != "sk-xxxx"
    ):
        logger.info(
            f"대용량 문서 감지 ({child_chunk_count} child chunks > {LARGE_DOC_CHUNK_THRESHOLD}) "
            f"— OpenAI {OPENAI_EMBEDDING_MODEL} (dim={PGVECTOR_DIMENSION}) 사용"
        )
        return _embed_text_openai, OPENAI_EMBEDDING_MODEL
    return _embed_text, EMBEDDING_MODEL


# ---------------------------------------------------------------------------
# PostgreSQL 저장 (SQLAlchemy)
# ---------------------------------------------------------------------------

async def _save_document(
    session: AsyncSession,
    state: "DocPipelineState",
    markdown_path: str,
    original_path: str,
) -> None:
    metadata = state.get("metadata") or {}
    await session.execute(
        text("""
            INSERT INTO documents (
                doc_id, title, source, category, file_type,
                file_path, markdown_path, storage_synced,
                neo4j_synced, upload_status, created_at,
                parser_used, doc_complexity, parsing_time_ms, original_filename
            )
            VALUES (
                :doc_id, :title, :source, :category, :file_type,
                :file_path, :markdown_path, TRUE, FALSE, 'processing', NOW(),
                :parser_used, :doc_complexity, :parsing_time_ms, :original_filename
            )
            ON CONFLICT (doc_id) DO UPDATE SET
                title             = EXCLUDED.title,
                source            = COALESCE(NULLIF(EXCLUDED.source, 'reprocess'), documents.source),
                category          = EXCLUDED.category,
                file_type         = COALESCE(EXCLUDED.file_type, documents.file_type),
                file_path         = COALESCE(NULLIF(EXCLUDED.file_path, ''), documents.file_path),
                markdown_path     = EXCLUDED.markdown_path,
                storage_synced    = TRUE,
                neo4j_synced      = FALSE,
                parser_used       = COALESCE(EXCLUDED.parser_used, documents.parser_used),
                doc_complexity    = COALESCE(EXCLUDED.doc_complexity, documents.doc_complexity),
                parsing_time_ms   = COALESCE(EXCLUDED.parsing_time_ms, documents.parsing_time_ms),
                original_filename = COALESCE(EXCLUDED.original_filename, documents.original_filename)
        """),
        {
            "doc_id": str(state["doc_id"]),
            "title": metadata.get("title") or state.get("original_filename", ""),
            "source": state.get("source", "upload"),
            "category": metadata.get("category", "기타"),
            "file_type": state.get("file_type") or None,
            "file_path": original_path,
            "markdown_path": markdown_path,
            "parser_used": state.get("parser_used"),
            "doc_complexity": state.get("doc_complexity"),
            "parsing_time_ms": state.get("parsing_time_ms"),
            "original_filename": state.get("original_filename"),
        },
    )


async def _save_chunks(
    session: AsyncSession,
    chunks: list[dict],
    doc_id: str,
) -> None:
    if not chunks:
        return
    rows = [
        {
            "chunk_id": str(chunk["chunk_id"]),
            "doc_id": doc_id,
            "parent_chunk_id": str(chunk["parent_chunk_id"]) if chunk.get("parent_chunk_id") else None,
            "chunk_type": chunk["chunk_type"],
            "content": chunk["content"],
            "token_count": chunk["token_count"],
            "page_number": chunk.get("page_number"),
            "section_header": chunk.get("section_header"),
        }
        for chunk in chunks
    ]
    await session.execute(
        text("""
            INSERT INTO chunks
                (chunk_id, doc_id, parent_chunk_id, chunk_type, content,
                 token_count, page_number, section_header)
            VALUES
                (:chunk_id, :doc_id, :parent_chunk_id, :chunk_type, :content,
                 :token_count, :page_number, :section_header)
            ON CONFLICT (chunk_id) DO NOTHING
        """),
        rows,
    )


async def _precompute_embeddings(
    chunks: list[dict],
) -> tuple[list[tuple[dict, list[float]]], str]:
    """child 청크 임베딩을 일괄 수집한다.

    chunk 수에 따라 Ollama(소규모) 또는 OpenAI(대규모)를 자동 선택한다.
    DB 트랜잭션 시작 전에 호출해야 한다 — HTTP 지연이 트랜잭션을 점유하지 않도록.

    Returns:
        (embedding rows, model_name_used)
    """
    child_chunks = [c for c in chunks if c["chunk_type"] == "child"]
    if not child_chunks:
        return [], EMBEDDING_MODEL

    embed_fn, model_name = _select_embed_fn(len(child_chunks))

    results = await asyncio.gather(
        *[embed_fn(c["content"]) for c in child_chunks],
        return_exceptions=True,
    )

    rows: list[tuple[dict, list[float]]] = []
    for chunk, result in zip(child_chunks, results):
        if isinstance(result, Exception):
            logger.warning(f"임베딩 생성 실패 (chunk={chunk['chunk_id']}): {result}")
            continue
        embedding: list[float] = result
        if len(embedding) != PGVECTOR_DIMENSION:
            raise RuntimeError(
                f"Embedding dimension mismatch: got {len(embedding)}, expected {PGVECTOR_DIMENSION}"
            )
        rows.append((chunk, embedding))

    if child_chunks and not rows:
        raise RuntimeError("No embeddings were saved for child chunks")

    logger.info(f"임베딩 사전 계산 완료: {len(rows)}/{len(child_chunks)}건 (model={model_name})")
    return rows, model_name


async def _insert_embedding_rows(
    session: AsyncSession,
    rows: list[tuple[dict, list[float]]],
    metadata: dict,
    model_name: str = EMBEDDING_MODEL,
) -> None:
    """사전 계산된 임베딩을 pgVector에 INSERT한다 (HTTP 호출 없음 — 트랜잭션 내부 전용)."""
    if not rows:
        return
    embed_rows = [
        {
            "chunk_id": str(chunk["chunk_id"]),
            "embedding": json.dumps(embedding),
            "model_name": model_name,
            "content": chunk["content"],
            "metadata": json.dumps(
                {
                    "category": metadata.get("category", "기타"),
                    "team": metadata.get("team"),
                    "tags": metadata.get("tags", []),
                    "section_header": chunk.get("section_header"),
                },
                ensure_ascii=False,
            ),
        }
        for chunk, embedding in rows
    ]
    await session.execute(
        text("""
            INSERT INTO chunk_embeddings (chunk_id, embedding, model_name, content, metadata)
            VALUES (:chunk_id, CAST(:embedding AS vector), :model_name, :content, CAST(:metadata AS jsonb))
            ON CONFLICT (chunk_id) DO UPDATE SET
                embedding = EXCLUDED.embedding,
                content   = EXCLUDED.content
        """),
        embed_rows,
    )


# ---------------------------------------------------------------------------
# Neo4j 저장
# ---------------------------------------------------------------------------

async def _save_to_neo4j(state: "DocPipelineState") -> bool:
    """Neo4j에 Document 노드, Chunk 노드, Entity 노드, MENTIONS 관계 저장.

    연결 실패는 경고만 남기고 무시한다.
    """
    if AsyncGraphDatabase is None:
        logger.warning("neo4j 패키지가 설치되지 않아 Neo4j 저장을 건너뜁니다.")
        return False

    metadata = state.get("metadata") or {}
    chunks = state.get("chunks") or []
    entities = state.get("neo4j_entities") or []
    relations = state.get("neo4j_relations") or []
    doc_id = state["doc_id"]

    try:
        driver = _get_neo4j_driver()
        async with driver.session() as neo_session:
            await neo_session.run(
                "MERGE (d:Document {doc_id: $doc_id}) "
                "SET d.title = $title, d.category = $category",
                doc_id=doc_id,
                title=metadata.get("title", ""),
                category=metadata.get("category", "기타"),
            )
            for chunk in chunks:
                await neo_session.run(
                    "MERGE (c:Chunk {chunk_id: $chunk_id}) "
                    "SET c.chunk_type = $chunk_type, c.section = $section "
                    "WITH c MATCH (d:Document {doc_id: $doc_id}) "
                    "MERGE (d)-[:HAS_CHUNK]->(c)",
                    chunk_id=chunk["chunk_id"],
                    chunk_type=chunk["chunk_type"],
                    section=chunk.get("section_header", ""),
                    doc_id=doc_id,
                )
            for entity in entities:
                await neo_session.run(
                    "MERGE (e:Entity {name: $name}) SET e.type = $type, e.description = $desc",
                    name=entity.get("name", ""),
                    type=entity.get("type", "Concept"),
                    desc=entity.get("description", ""),
                )
            for rel in relations:
                await neo_session.run(
                    "MATCH (c:Chunk {chunk_id: $chunk_id}) "
                    "MATCH (e:Entity {name: $entity_name}) "
                    "MERGE (c)-[:MENTIONS]->(e)",
                    chunk_id=rel["from_chunk_id"],
                    entity_name=rel["entity_name"],
                )
        logger.info("Neo4j 저장 완료", extra={"doc_id": doc_id})
        return True
    except Exception as e:
        logger.warning(f"Neo4j 저장 실패 (파이프라인 계속): {e}", extra={"doc_id": doc_id})
        return False


# ---------------------------------------------------------------------------
# Stage 6 노드 함수
# ---------------------------------------------------------------------------

async def stage6_store(
    state: "DocPipelineState",
    db_session_factory: async_sessionmaker[AsyncSession],
    storage: "Storage",
) -> dict:
    """LangGraph 노드: PostgreSQL + pgVector + Storage + Neo4j 저장."""
    doc_id = state["doc_id"]
    chunks = state.get("chunks") or []
    metadata = state.get("metadata") or {}

    logger.info("Stage 6 시작", extra={"doc_id": doc_id})

    # --- 1. 원본 파일을 storage에 복사 ---
    file_path = state.get("file_path") or ""
    original_filename = state.get("original_filename") or "file"
    original_path = f"originals/{doc_id}/{original_filename}"

    if file_path:
        try:
            async with aiofiles.open(file_path, "rb") as f:
                content = await f.read()
            await storage.save(original_path, content)
        except Exception as e:
            logger.error(f"원본 파일 저장 실패: {e}", extra={"doc_id": doc_id})
            return {
                "stored": False,
                "status": "failed",
                "error": f"Stage6 원본 저장 실패: {e}",
                "current_stage": "stage6_store",
            }
    else:
        existing_paths = state.get("storage_paths") or {}
        original_path = existing_paths.get("original", original_path)
        logger.info("재처리 — 원본 파일 저장 생략", extra={"doc_id": doc_id})

    markdown_path = state.get("markdown_storage_path", f"markdown/{doc_id}/raw.md")

    # --- 2. 임베딩 사전 계산 (트랜잭션 시작 전 — Ollama/OpenAI HTTP 호출) ---
    try:
        embedding_rows, embed_model = await _precompute_embeddings(chunks)
    except RuntimeError as e:
        logger.error(f"임베딩 사전 계산 실패 — DB 저장 중단: {e}", extra={"doc_id": doc_id})
        return {
            "stored": False,
            "status": "failed",
            "error": f"Stage6 임베딩 실패: {e}",
            "current_stage": "stage6_store",
        }

    # --- 3. PostgreSQL 저장 (트랜잭션 — 순수 DB INSERT만) ---
    try:
        async with db_session_factory() as session:
            async with session.begin():
                await _save_document(session, state, markdown_path, original_path)
                await _save_chunks(session, chunks, doc_id)
                await _insert_embedding_rows(session, embedding_rows, metadata, embed_model)
    except Exception as e:
        logger.error(f"PostgreSQL 저장 실패: {e}", extra={"doc_id": doc_id})
        return {
            "stored": False,
            "status": "failed",
            "error": f"Stage6 DB 저장 실패: {e}",
            "current_stage": "stage6_store",
        }

    # --- 4. Neo4j 저장 (실패해도 파이프라인 계속) ---
    neo4j_ok = await _save_to_neo4j(state)

    async with db_session_factory() as session:
        await session.execute(
            text("UPDATE documents SET neo4j_synced = :val WHERE doc_id = :doc_id"),
            {"val": neo4j_ok, "doc_id": doc_id},
        )
        await session.commit()

    final_status = "stored" if neo4j_ok else "stored_partial"
    if not neo4j_ok:
        logger.warning("Neo4j 저장 실패 — stored_partial 로 처리", extra={"doc_id": doc_id})

    logger.info(f"Stage 6 완료 (status={final_status})", extra={"doc_id": doc_id})
    return {
        "stored": True,
        "neo4j_stored": neo4j_ok,
        "storage_paths": {
            "original": original_path,
            "markdown": markdown_path,
        },
        "status": final_status,
        "current_stage": "stage6_store",
    }
