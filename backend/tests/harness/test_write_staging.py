"""G5: write_staging_draft usecase 통합 테스트."""

import uuid
import pytest

from app.domain.models import ConceptExtractionSchema, ConceptDomain
from app.usecases.write_staging_draft import write_staging_draft


# ── 테스트 데이터 ────────────────────────────────────────────────────────────

def _make_concept(name: str, description_ko: str = "설명", domain: str = "security") -> ConceptExtractionSchema:
    return ConceptExtractionSchema(
        concept_name=name,
        concept_domain=domain,
        severity="HIGH",
        description_ko=description_ko,
    )


async def _insert_doc(conn, doc_id: str) -> None:
    await conn.execute(
        "INSERT INTO documents (doc_id, url) VALUES ($1, $2) ON CONFLICT DO NOTHING",
        doc_id,
        "https://example.com/write-staging-test",
    )


async def _cleanup(conn, session_id: str, doc_id: str) -> None:
    await conn.execute(
        "DELETE FROM staging_concepts WHERE session_id = $1::uuid", session_id
    )
    await conn.execute("DELETE FROM documents WHERE doc_id = $1", doc_id)


# ── T_write_draft_inserts ────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_write_draft_inserts(asyncpg_pool):
    """2개 concept → DB에 2행, status='DRAFT'."""
    session_id = str(uuid.uuid4())
    doc_id = f"EXT_wsd_{uuid.uuid4().hex[:8]}"

    async with asyncpg_pool.acquire() as conn:
        await _insert_doc(conn, doc_id)
        try:
            concepts = [_make_concept("XSS"), _make_concept("SQLI")]
            await write_staging_draft(session_id, doc_id, concepts, conn)

            rows = await conn.fetch(
                "SELECT status FROM staging_concepts WHERE session_id = $1::uuid",
                session_id,
            )
            assert len(rows) == 2
            assert all(r["status"] == "DRAFT" for r in rows)
        finally:
            await _cleanup(conn, session_id, doc_id)


# ── T_write_draft_json ───────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_write_draft_json(asyncpg_pool):
    """description_ko 값이 DB에 올바르게 저장된다."""
    session_id = str(uuid.uuid4())
    doc_id = f"EXT_wsd_{uuid.uuid4().hex[:8]}"

    async with asyncpg_pool.acquire() as conn:
        await _insert_doc(conn, doc_id)
        try:
            concepts = [_make_concept("XSS", description_ko="테스트")]
            await write_staging_draft(session_id, doc_id, concepts, conn)

            value = await conn.fetchval(
                "SELECT description_ko FROM staging_concepts WHERE session_id = $1::uuid",
                session_id,
            )
            assert value == "테스트"
        finally:
            await _cleanup(conn, session_id, doc_id)


# ── T_write_draft_count ──────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_write_draft_count(asyncpg_pool):
    """3개 concept → 반환값 == 3."""
    session_id = str(uuid.uuid4())
    doc_id = f"EXT_wsd_{uuid.uuid4().hex[:8]}"

    async with asyncpg_pool.acquire() as conn:
        await _insert_doc(conn, doc_id)
        try:
            concepts = [_make_concept(f"C{i}") for i in range(3)]
            count = await write_staging_draft(session_id, doc_id, concepts, conn)
            assert count == 3
        finally:
            await _cleanup(conn, session_id, doc_id)
