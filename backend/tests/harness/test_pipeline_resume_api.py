"""POST /api/pipeline/{session_id}/resume 통합 테스트."""

import uuid
from unittest.mock import patch

import pytest
import httpx
from fastapi import FastAPI

from app.interfaces.api.pipeline import router
from app.interfaces.api._deps import get_conn


# ── 테스트 앱 팩토리 ──────────────────────────────────────────────────────────

def _make_test_app(conn) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_conn] = lambda: conn
    return app


# ── DB 헬퍼 ───────────────────────────────────────────────────────────────────

async def _insert_doc(conn, doc_id: str, state: str) -> None:
    await conn.execute(
        "INSERT INTO knowledge_document (doc_id, source_prefix, original_url, content_hash, state) "
        "VALUES ($1,'EXT','https://example.com/resume-test','bb000000', $2) ON CONFLICT DO NOTHING",
        doc_id, state,
    )


async def _insert_log(
    conn, doc_id: str, session_id: str, agent: str, level: str, message: str
) -> None:
    await conn.execute(
        "INSERT INTO pipeline_logs (doc_id, session_id, agent, level, message) "
        "VALUES ($1, $2::uuid, $3, $4, $5)",
        doc_id, session_id, agent, level, message,
    )


async def _insert_staging(conn, doc_id: str, session_id: str, state: str) -> None:
    await conn.execute(
        "INSERT INTO staging_concepts (session_id, doc_id, concept_json, state) "
        "VALUES ($1::uuid, $2, $3::jsonb, $4)",
        session_id, doc_id, '{"name": "TestConcept"}', state,
    )


async def _cleanup(conn, session_id: str, doc_id: str) -> None:
    await conn.execute(
        "DELETE FROM staging_concepts WHERE session_id = $1::uuid", session_id
    )
    await conn.execute(
        "DELETE FROM pipeline_logs WHERE session_id = $1::uuid", session_id
    )
    await conn.execute("DELETE FROM knowledge_document WHERE doc_id = $1", doc_id)


# ── T1: resume_step 2 (Crawler) → crawl_task 재호출 ────────────────────────────

@pytest.mark.anyio
async def test_resume_step2_triggers_crawl_task(asyncpg_pool):
    """FAILED 문서 + resume_step=2 → 200, [RESUME] 로그 삽입, crawl_task.delay 호출."""
    session_id = str(uuid.uuid4())
    doc_id = f"EXT_resume_{uuid.uuid4().hex[:8]}"

    async with asyncpg_pool.acquire() as conn:
        await _insert_doc(conn, doc_id, "FAILED")
        await _insert_log(conn, doc_id, session_id, "Crawler", "ERROR", "크롤링 실패")
        try:
            app = _make_test_app(conn)
            with patch("app.worker.tasks.crawl_task.delay") as mock_crawl:
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:
                    resp = await client.post(
                        f"/api/pipeline/{session_id}/resume", json={"resume_step": 2}
                    )

            assert resp.status_code == 200
            body = resp.json()
            assert body["session_id"] == session_id
            assert body["doc_id"] == doc_id
            assert body["resumed_step"] == 2
            mock_crawl.assert_called_once_with(session_id=session_id, doc_id=doc_id)

            rows = await conn.fetch(
                "SELECT message FROM pipeline_logs WHERE session_id=$1::uuid AND agent='System' "
                "ORDER BY created_at DESC LIMIT 1",
                session_id,
            )
            assert "[RESUME]" in rows[0]["message"]
        finally:
            await _cleanup(conn, session_id, doc_id)


# ── T2: 비-FAILED 문서 → 409 ────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_resume_requires_failed_state(asyncpg_pool):
    """knowledge_document.state != FAILED → 409."""
    session_id = str(uuid.uuid4())
    doc_id = f"EXT_resume_{uuid.uuid4().hex[:8]}"

    async with asyncpg_pool.acquire() as conn:
        await _insert_doc(conn, doc_id, "CRAWLING")
        await _insert_log(conn, doc_id, session_id, "Crawler", "INFO", "크롤링 진행 중")
        try:
            app = _make_test_app(conn)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    f"/api/pipeline/{session_id}/resume", json={"resume_step": 2}
                )

            assert resp.status_code == 409
        finally:
            await _cleanup(conn, session_id, doc_id)


# ── T3: resume_step 5 + APPROVED 스테이징 없음 → 409 ───────────────────────────

@pytest.mark.anyio
async def test_resume_step5_without_approved_staging(asyncpg_pool):
    """FAILED 문서 + resume_step=5 + APPROVED 스테이징 없음 → 409."""
    session_id = str(uuid.uuid4())
    doc_id = f"EXT_resume_{uuid.uuid4().hex[:8]}"

    async with asyncpg_pool.acquire() as conn:
        await _insert_doc(conn, doc_id, "FAILED")
        await _insert_log(conn, doc_id, session_id, "Writer", "ERROR", "그래프 적재 실패")
        try:
            app = _make_test_app(conn)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    f"/api/pipeline/{session_id}/resume", json={"resume_step": 5}
                )

            assert resp.status_code == 409
        finally:
            await _cleanup(conn, session_id, doc_id)


# ── T4: resume_step 5 + APPROVED 스테이징 존재 → write_graph_task 재호출 ───────

@pytest.mark.anyio
async def test_resume_step5_with_approved_staging(asyncpg_pool):
    """FAILED 문서 + resume_step=5 + APPROVED 스테이징 → 200, write_graph_task.delay 호출."""
    session_id = str(uuid.uuid4())
    doc_id = f"EXT_resume_{uuid.uuid4().hex[:8]}"

    async with asyncpg_pool.acquire() as conn:
        await _insert_doc(conn, doc_id, "FAILED")
        await _insert_log(conn, doc_id, session_id, "Writer", "ERROR", "그래프 적재 실패")
        await _insert_staging(conn, doc_id, session_id, "APPROVED")
        try:
            app = _make_test_app(conn)
            with patch("app.worker.tasks.write_graph_task.delay") as mock_write:
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:
                    resp = await client.post(
                        f"/api/pipeline/{session_id}/resume", json={"resume_step": 5}
                    )

            assert resp.status_code == 200
            assert resp.json()["resumed_step"] == 5
            mock_write.assert_called_once_with(session_id=session_id, doc_id=doc_id)
        finally:
            await _cleanup(conn, session_id, doc_id)


# ── T5: 알 수 없는 session_id → 404 ────────────────────────────────────────────

@pytest.mark.anyio
async def test_resume_unknown_session(asyncpg_pool):
    """존재하지 않는 session_id → 404."""
    unknown = str(uuid.uuid4())

    async with asyncpg_pool.acquire() as conn:
        app = _make_test_app(conn)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/pipeline/{unknown}/resume", json={"resume_step": 2}
            )

    assert resp.status_code == 404


# ── T6: 잘못된 resume_step → 400 ───────────────────────────────────────────────

@pytest.mark.anyio
async def test_resume_invalid_step(asyncpg_pool):
    """FAILED 문서 + resume_step=99 (범위 밖) → 400."""
    session_id = str(uuid.uuid4())
    doc_id = f"EXT_resume_{uuid.uuid4().hex[:8]}"

    async with asyncpg_pool.acquire() as conn:
        await _insert_doc(conn, doc_id, "FAILED")
        await _insert_log(conn, doc_id, session_id, "Crawler", "ERROR", "크롤링 실패")
        try:
            app = _make_test_app(conn)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    f"/api/pipeline/{session_id}/resume", json={"resume_step": 99}
                )

            assert resp.status_code == 400
        finally:
            await _cleanup(conn, session_id, doc_id)
