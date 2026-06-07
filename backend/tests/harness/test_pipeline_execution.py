"""파이프라인 실행 TDD — 통합 테스트 (RED → GREEN 사이클).

T_exec_01: prescan이 documents.infer_confidence를 업데이트한다
T_exec_02: trigger가 pipeline_logs(session_id, agent, level) 행을 삽입한다
T_exec_03: trigger가 documents.state를 PENDING → CRAWLING으로 전이한다
T_exec_04: 로그 폴링이 doc_state를 올바르게 반환한다
T_exec_05: prescan + trigger + logs 전체 시퀀스가 순서대로 동작한다
T_exec_06: 이미 CRAWLING인 문서를 trigger하면 409를 반환한다
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.interfaces.api._deps import get_conn
from app.interfaces.api.pipeline import router as pipeline_router
from app.interfaces.api.prescan import router as prescan_router


# ── 앱 팩토리 ────────────────────────────────────────────────────────────────

def _make_app(conn) -> FastAPI:
    app = FastAPI()
    app.include_router(prescan_router)
    app.include_router(pipeline_router)
    app.dependency_overrides[get_conn] = lambda: conn
    return app


# ── DB 헬퍼 ──────────────────────────────────────────────────────────────────

async def _insert_doc(conn, doc_id: str, state: str = "PENDING") -> None:
    await conn.execute(
        """INSERT INTO documents
               (doc_id, source_prefix, original_url, content_hash, state)
           VALUES ($1, 'EXT',
                   'https://docs.djangoproject.com/en/6.0/topics/security/',
                   'aa000000', $2)
           ON CONFLICT DO NOTHING""",
        doc_id, state,
    )


async def _cleanup(conn, doc_id: str) -> None:
    await conn.execute(
        "DELETE FROM pipeline_logs WHERE doc_id = $1", doc_id
    )
    await conn.execute(
        "DELETE FROM staging_concepts WHERE doc_id = $1", doc_id
    )
    await conn.execute(
        "DELETE FROM documents WHERE doc_id = $1", doc_id
    )


# ── T_exec_01: prescan이 infer_confidence를 DB에 저장 ────────────────────────

@pytest.mark.anyio
async def test_exec_01_prescan_updates_infer_confidence(asyncpg_pool):
    """prescan 엔드포인트가 documents.infer_confidence 컬럼을 업데이트한다.

    RED 조건: documents 테이블에 infer_confidence 컬럼이 없으면 500 발생.
    GREEN 조건: schema.sql에 컬럼 추가 후 0.0 이상 값이 저장된다.
    """
    doc_id = f"EXT_exec01_{uuid.uuid4().hex[:8]}"

    async with asyncpg_pool.acquire() as conn:
        await _insert_doc(conn, doc_id)

        mock_html = (
            '<html lang="en"><head><title>Django 6.0 Security</title></head>'
            "<body></body></html>"
        )

        try:
            app = _make_app(conn)

            with patch("app.interfaces.api.prescan.httpx") as mock_httpx:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.text = mock_html
                mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(
                    return_value=mock_httpx.AsyncClient.return_value
                )
                mock_httpx.AsyncClient.return_value.__aexit__ = AsyncMock(return_value=False)
                mock_httpx.AsyncClient.return_value.get = AsyncMock(return_value=mock_resp)
                mock_httpx.HTTPError = httpx.HTTPError

                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    resp = await client.post(f"/api/documents/{doc_id}/prescan")

            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert "infer_confidence" in body
            assert body["infer_confidence"] >= 0.0

            # DB에 실제로 저장됐는지 확인
            row = await conn.fetchrow(
                "SELECT infer_confidence FROM documents WHERE doc_id=$1", doc_id
            )
            assert row is not None
            assert row["infer_confidence"] is not None
            assert row["infer_confidence"] >= 0.0

        finally:
            await _cleanup(conn, doc_id)


# ── T_exec_02: trigger가 pipeline_logs 행을 올바른 컬럼으로 삽입 ──────────────

@pytest.mark.anyio
async def test_exec_02_trigger_inserts_pipeline_log(asyncpg_pool):
    """pipeline trigger가 pipeline_logs에 session_id, agent, level 행을 삽입한다.

    RED 조건: pipeline_logs에 session_id/agent/level 컬럼이 없으면 500 발생.
    GREEN 조건: INSERT 성공 후 로그 행 ≥ 1.
    """
    doc_id = f"EXT_exec02_{uuid.uuid4().hex[:8]}"

    async with asyncpg_pool.acquire() as conn:
        await _insert_doc(conn, doc_id, "PENDING")

        try:
            app = _make_app(conn)

            with patch("app.interfaces.api.pipeline.run_pipeline_task"):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    resp = await client.post(
                        "/api/pipeline/trigger",
                        json={"doc_id": doc_id},
                    )

            assert resp.status_code == 202, resp.text
            session_id = resp.json()["session_id"]

            row = await conn.fetchrow(
                "SELECT agent, level, message FROM pipeline_logs "
                "WHERE session_id=$1::uuid",
                session_id,
            )
            assert row is not None, "pipeline_logs 행이 존재해야 함"
            assert row["agent"] is not None
            assert row["level"] is not None

        finally:
            await _cleanup(conn, doc_id)


# ── T_exec_03: trigger가 documents.state를 CRAWLING으로 전이 ─────────────────

@pytest.mark.anyio
async def test_exec_03_trigger_transitions_state_to_crawling(asyncpg_pool):
    """trigger 후 documents.state가 PENDING → CRAWLING으로 전이된다."""
    doc_id = f"EXT_exec03_{uuid.uuid4().hex[:8]}"

    async with asyncpg_pool.acquire() as conn:
        await _insert_doc(conn, doc_id, "PENDING")

        try:
            app = _make_app(conn)

            with patch("app.interfaces.api.pipeline.run_pipeline_task"):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    resp = await client.post(
                        "/api/pipeline/trigger",
                        json={"doc_id": doc_id},
                    )

            assert resp.status_code == 202

            row = await conn.fetchrow(
                "SELECT state FROM documents WHERE doc_id=$1", doc_id
            )
            assert row["state"] == "CRAWLING"

        finally:
            await _cleanup(conn, doc_id)


# ── T_exec_04: 로그 폴링이 doc_state를 반환 ──────────────────────────────────

@pytest.mark.anyio
async def test_exec_04_logs_poll_returns_doc_state(asyncpg_pool):
    """GET /api/pipeline/logs/{session_id}가 현재 doc_state를 반환한다."""
    doc_id = f"EXT_exec04_{uuid.uuid4().hex[:8]}"
    session_id = str(uuid.uuid4())

    async with asyncpg_pool.acquire() as conn:
        await _insert_doc(conn, doc_id, "EXTRACTED")
        await conn.execute(
            "INSERT INTO pipeline_logs (doc_id, session_id, agent, level, message) "
            "VALUES ($1, $2::uuid, 'Extractor', 'INFO', '추출 완료')",
            doc_id, session_id,
        )

        try:
            app = _make_app(conn)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(f"/api/pipeline/logs/{session_id}")

            assert resp.status_code == 200
            body = resp.json()
            assert body["doc_state"] == "EXTRACTED"
            assert len(body["logs"]) >= 1
            assert body["logs"][0]["agent"] == "Extractor"

        finally:
            await conn.execute(
                "DELETE FROM pipeline_logs WHERE session_id=$1::uuid", session_id
            )
            await _cleanup(conn, doc_id)


# ── T_exec_05: 전체 시퀀스 — prescan → trigger → poll ────────────────────────

@pytest.mark.anyio
async def test_exec_05_full_pipeline_sequence(asyncpg_pool):
    """prescan → trigger → logs 폴링 전체 시퀀스가 순서대로 동작한다."""
    doc_id = f"EXT_exec05_{uuid.uuid4().hex[:8]}"

    async with asyncpg_pool.acquire() as conn:
        await _insert_doc(conn, doc_id, "PENDING")

        mock_html = (
            '<html lang="en"><head><title>Django 6.0</title></head><body></body></html>'
        )

        try:
            app = _make_app(conn)

            # Step 1: prescan
            with patch("app.interfaces.api.prescan.httpx") as mock_httpx:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.text = mock_html
                mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(
                    return_value=mock_httpx.AsyncClient.return_value
                )
                mock_httpx.AsyncClient.return_value.__aexit__ = AsyncMock(return_value=False)
                mock_httpx.AsyncClient.return_value.get = AsyncMock(return_value=mock_resp)
                mock_httpx.HTTPError = httpx.HTTPError

                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    ps_resp = await client.post(f"/api/documents/{doc_id}/prescan")

            assert ps_resp.status_code == 200, ps_resp.text
            assert ps_resp.json()["framework"] == "Django"

            # Step 2: trigger
            with patch("app.interfaces.api.pipeline.run_pipeline_task"):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    trig_resp = await client.post(
                        "/api/pipeline/trigger", json={"doc_id": doc_id}
                    )

            assert trig_resp.status_code == 202
            session_id = trig_resp.json()["session_id"]

            # Step 3: 상태 확인
            doc_row = await conn.fetchrow(
                "SELECT state FROM documents WHERE doc_id=$1", doc_id
            )
            assert doc_row["state"] == "CRAWLING"

            # Step 4: logs 폴링
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                log_resp = await client.get(f"/api/pipeline/logs/{session_id}")

            assert log_resp.status_code == 200
            assert log_resp.json()["doc_state"] == "CRAWLING"

        finally:
            await _cleanup(conn, doc_id)


# ── T_exec_06: 이미 CRAWLING인 문서 trigger → 409 ────────────────────────────

@pytest.mark.anyio
async def test_exec_06_trigger_non_pending_returns_409(asyncpg_pool):
    """CRAWLING 상태 문서를 다시 trigger하면 409 Conflict를 반환한다."""
    doc_id = f"EXT_exec06_{uuid.uuid4().hex[:8]}"

    async with asyncpg_pool.acquire() as conn:
        await _insert_doc(conn, doc_id, "CRAWLING")

        try:
            app = _make_app(conn)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/pipeline/trigger", json={"doc_id": doc_id}
                )

            assert resp.status_code == 409

        finally:
            await _cleanup(conn, doc_id)
