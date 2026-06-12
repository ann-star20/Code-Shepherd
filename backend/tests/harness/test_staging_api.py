"""G7: Staging Gate API 엔드포인트 통합 테스트."""

import json
import uuid

import httpx
import pytest
from app.interfaces.api.staging import _get_conn, router
from fastapi import FastAPI

# ── 테스트 앱 팩토리 ──────────────────────────────────────────────────────────


def _make_test_app(conn) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_get_conn] = lambda: conn
    return app


# ── DB 헬퍼 ───────────────────────────────────────────────────────────────────


async def _insert_doc(conn, doc_id: str) -> None:
    await conn.execute(
        "INSERT INTO knowledge_documents (doc_id, source_prefix, original_url, content_hash) "
        "VALUES ($1,'EXT','https://example.com/staging-api-test','abcd1234') ON CONFLICT DO NOTHING",
        doc_id,
    )


def _make_concept_json(name: str) -> str:
    return json.dumps(
        {
            "concept_name": name,
            "domains": ["security"],
            "severity": "high",
            "description_ko": "테스트",
            "aliases": [],
        }
    )


async def _insert_draft(conn, session_id: str, doc_id: str, name: str) -> None:
    cj = _make_concept_json(name)
    await conn.execute(
        """INSERT INTO staging_concepts
           (session_id, doc_id, concept_json, state, known_domains, unknown_domains)
           VALUES ($1::uuid, $2, $3::jsonb, 'DRAFT', $4, '{}')""",
        session_id,
        doc_id,
        cj,
        ["security"],
    )


async def _cleanup(conn, session_id: str, doc_id: str) -> None:
    await conn.execute(
        "DELETE FROM staging_concepts WHERE session_id = $1::uuid", session_id
    )
    await conn.execute("DELETE FROM knowledge_documents WHERE doc_id = $1", doc_id)


# ── T_get_staging_list ────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_get_staging_list(asyncpg_pool):
    """2행 DRAFT → GET /{session_id} → 200, items 길이 2."""
    session_id = str(uuid.uuid4())
    doc_id = f"EXT_api_{uuid.uuid4().hex[:8]}"

    async with asyncpg_pool.acquire() as conn:
        await _insert_doc(conn, doc_id)
        await _insert_draft(conn, session_id, doc_id, "XSS")
        await _insert_draft(conn, session_id, doc_id, "SQLI")
        try:
            app = _make_test_app(conn)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(f"/api/staging/{session_id}")

            assert resp.status_code == 200
            assert len(resp.json()["items"]) == 2
        finally:
            await _cleanup(conn, session_id, doc_id)


# ── T_reject_clears_draft ─────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_reject_clears_draft(asyncpg_pool):
    """3행 DRAFT → POST /{session_id}/reject → {"rejected":3}, DB 행 0."""
    session_id = str(uuid.uuid4())
    doc_id = f"EXT_api_{uuid.uuid4().hex[:8]}"

    async with asyncpg_pool.acquire() as conn:
        await _insert_doc(conn, doc_id)
        for i in range(3):
            await _insert_draft(conn, session_id, doc_id, f"C{i}")
        try:
            app = _make_test_app(conn)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(f"/api/staging/{session_id}/reject")

            assert resp.status_code == 200
            assert resp.json() == {"rejected": 3}

            remaining = await conn.fetchval(
                "SELECT count(*) FROM staging_concepts WHERE session_id = $1::uuid",
                session_id,
            )
            assert remaining == 0
        finally:
            await _cleanup(conn, session_id, doc_id)


# ── T_diff_counts ─────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_diff_counts(asyncpg_pool):
    """2 DRAFT + 1 APPROVED → GET /{session_id}/diff → 올바른 카운트."""
    session_id = str(uuid.uuid4())
    doc_id = f"EXT_api_{uuid.uuid4().hex[:8]}"

    async with asyncpg_pool.acquire() as conn:
        await _insert_doc(conn, doc_id)
        await _insert_draft(conn, session_id, doc_id, "XSS")
        await _insert_draft(conn, session_id, doc_id, "SQLI")
        cj = _make_concept_json("CSRF")
        await conn.execute(
            """INSERT INTO staging_concepts
               (session_id, doc_id, concept_json, state, known_domains, unknown_domains)
               VALUES ($1::uuid, $2, $3::jsonb, 'APPROVED', $4, '{}')""",
            session_id,
            doc_id,
            cj,
            ["security"],
        )
        try:
            app = _make_test_app(conn)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(f"/api/staging/{session_id}/diff")

            assert resp.status_code == 200
            data = resp.json()
            assert data["draft"] == 2
            assert data["approved"] == 1
            assert data["committed"] == 0
        finally:
            await _cleanup(conn, session_id, doc_id)
