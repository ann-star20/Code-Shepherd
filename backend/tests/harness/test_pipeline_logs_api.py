"""A2-T1: GET /api/pipeline/logs/{session_id} 통합 테스트."""

import uuid
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

async def _insert_doc(conn, doc_id: str, state: str = "CRAWLING") -> None:
    await conn.execute(
        "INSERT INTO knowledge_document (doc_id, source_prefix, original_url, content_hash, state) "
        "VALUES ($1,'EXT','https://example.com/log-test','aa000000', $2) ON CONFLICT DO NOTHING",
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


async def _cleanup(conn, session_id: str, doc_id: str) -> None:
    await conn.execute(
        "DELETE FROM pipeline_logs WHERE session_id = $1::uuid", session_id
    )
    await conn.execute("DELETE FROM knowledge_document WHERE doc_id = $1", doc_id)


# ── T1: 로그 행 반환 ──────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_logs_returns_rows(asyncpg_pool):
    """2개 로그 행 → GET /logs/{session_id} → 200, logs 길이 2."""
    session_id = str(uuid.uuid4())
    doc_id = f"EXT_log_{uuid.uuid4().hex[:8]}"

    async with asyncpg_pool.acquire() as conn:
        await _insert_doc(conn, doc_id, "CRAWLING")
        await _insert_log(conn, doc_id, session_id, "Crawler", "INFO", "크롤링 시작")
        await _insert_log(conn, doc_id, session_id, "Crawler", "INFO", "크롤링 완료")
        try:
            app = _make_test_app(conn)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(f"/api/pipeline/logs/{session_id}")

            assert resp.status_code == 200
            body = resp.json()
            assert body["session_id"] == session_id
            assert len(body["logs"]) == 2
        finally:
            await _cleanup(conn, session_id, doc_id)


# ── T2: doc_state 반영 ────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_logs_includes_doc_state(asyncpg_pool):
    """knowledge_document.state = EXTRACTED → response.doc_state == EXTRACTED."""
    session_id = str(uuid.uuid4())
    doc_id = f"EXT_log_{uuid.uuid4().hex[:8]}"

    async with asyncpg_pool.acquire() as conn:
        await _insert_doc(conn, doc_id, "EXTRACTED")
        await _insert_log(conn, doc_id, session_id, "Extractor", "INFO", "추출 완료")
        try:
            app = _make_test_app(conn)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(f"/api/pipeline/logs/{session_id}")

            assert resp.status_code == 200
            assert resp.json()["doc_state"] == "EXTRACTED"
        finally:
            await _cleanup(conn, session_id, doc_id)


# ── T3: 알 수 없는 세션 → 빈 배열 ─────────────────────────────────────────────

@pytest.mark.anyio
async def test_logs_empty_for_unknown_session(asyncpg_pool):
    """존재하지 않는 session_id → 200, logs=[], doc_state=None."""
    unknown = str(uuid.uuid4())

    async with asyncpg_pool.acquire() as conn:
        app = _make_test_app(conn)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(f"/api/pipeline/logs/{unknown}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["logs"] == []
    assert body["doc_state"] is None


# ── T4: 로그 필드 구조 검증 ───────────────────────────────────────────────────

@pytest.mark.anyio
async def test_log_entry_fields(asyncpg_pool):
    """각 로그 항목에 ts, agent, level, message 필드 존재."""
    session_id = str(uuid.uuid4())
    doc_id = f"EXT_log_{uuid.uuid4().hex[:8]}"

    async with asyncpg_pool.acquire() as conn:
        await _insert_doc(conn, doc_id)
        await _insert_log(conn, doc_id, session_id, "Writer", "WARNING", "노드 중복")
        try:
            app = _make_test_app(conn)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(f"/api/pipeline/logs/{session_id}")

            entry = resp.json()["logs"][0]
            assert "ts" in entry
            assert entry["agent"] == "Writer"
            assert entry["level"] == "WARNING"
            assert entry["message"] == "노드 중복"
        finally:
            await _cleanup(conn, session_id, doc_id)
