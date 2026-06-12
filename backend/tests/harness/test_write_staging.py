"""write_staging_draft — JSONB v2 + DOMAIN_PENDING 분류 테스트 (Phase 2 SDD T_ws_01~03).

SDD 스펙:
  - concept_json JSONB 저장 (개별 컬럼 아님)
  - 등록 도메인 → state='DRAFT', known_domains 채움
  - 미등록 도메인 → state='DOMAIN_PENDING', unknown_domains 채움
  - registered_domains=None → 분류 없이 DRAFT
"""

import json
import uuid

import pytest
from app.domain.models import ConceptExtractionSchema
from app.usecases.write_staging_draft import write_staging_draft


def _parse_jsonb(val) -> dict:
    """asyncpg는 JSONB를 str로 반환 — dict로 변환."""
    return json.loads(val) if isinstance(val, str) else val


def _concept(name: str, domains: list[str]) -> ConceptExtractionSchema:
    return ConceptExtractionSchema(
        concept_name=name,
        domains=domains,
        severity="high",
        description_ko="설명",
    )


async def _doc(conn, doc_id: str) -> None:
    await conn.execute(
        "INSERT INTO knowledge_documents (doc_id, source_prefix, original_url, content_hash) "
        "VALUES ($1,'EXT','https://test.example.com','abcd1234') ON CONFLICT DO NOTHING",
        doc_id,
    )


async def _cleanup(conn, session_id: str, doc_id: str) -> None:
    await conn.execute(
        "DELETE FROM staging_concepts WHERE session_id=$1::uuid", session_id
    )
    await conn.execute("DELETE FROM knowledge_documents WHERE doc_id=$1", doc_id)


# T_ws_01: 등록 도메인 → state='DRAFT', concept_json 저장
@pytest.mark.anyio
async def test_ws_draft_insert(asyncpg_pool):
    sid = str(uuid.uuid4())
    did = f"EXT_ws_{uuid.uuid4().hex[:8]}"
    async with asyncpg_pool.acquire() as conn:
        await _doc(conn, did)
        try:
            n = await write_staging_draft(
                sid, did, [_concept("XSS", ["security"])], conn, {"security"}
            )
            assert n == 1
            row = await conn.fetchrow(
                "SELECT state, known_domains, unknown_domains, concept_json "
                "FROM staging_concepts WHERE session_id=$1::uuid",
                sid,
            )
            assert row["state"] == "DRAFT"
            assert "security" in row["known_domains"]
            assert list(row["unknown_domains"]) == []
            cj = _parse_jsonb(row["concept_json"])
            assert cj["concept_name"] == "XSS"
        finally:
            await _cleanup(conn, sid, did)


# T_ws_02: 미등록 도메인 → state='DOMAIN_PENDING'
@pytest.mark.anyio
async def test_ws_domain_pending(asyncpg_pool):
    sid = str(uuid.uuid4())
    did = f"EXT_ws_{uuid.uuid4().hex[:8]}"
    async with asyncpg_pool.acquire() as conn:
        await _doc(conn, did)
        try:
            await write_staging_draft(
                sid,
                did,
                [_concept("GDPR", ["compliance"])],
                conn,
                {"security", "performance"},
            )
            row = await conn.fetchrow(
                "SELECT state, unknown_domains FROM staging_concepts WHERE session_id=$1::uuid",
                sid,
            )
            assert row["state"] == "DOMAIN_PENDING"
            assert "compliance" in row["unknown_domains"]
        finally:
            await _cleanup(conn, sid, did)


# T_ws_03: registered_domains=None → 항상 DRAFT (분류 없음)
@pytest.mark.anyio
async def test_ws_no_registry_defaults_draft(asyncpg_pool):
    sid = str(uuid.uuid4())
    did = f"EXT_ws_{uuid.uuid4().hex[:8]}"
    async with asyncpg_pool.acquire() as conn:
        await _doc(conn, did)
        try:
            n = await write_staging_draft(
                sid, did, [_concept("X", ["unknown_domain"])], conn, None
            )
            assert n == 1
            row = await conn.fetchrow(
                "SELECT state FROM staging_concepts WHERE session_id=$1::uuid", sid
            )
            assert row["state"] == "DRAFT"
        finally:
            await _cleanup(conn, sid, did)
