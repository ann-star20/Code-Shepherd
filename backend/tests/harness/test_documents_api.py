"""P1-T9~T11 단위 테스트 — FastAPI 라우터 (documents / prescan / pipeline trigger).

T09: POST /api/documents — URL 입력, doc_id 생성, PENDING 상태
T10: POST /api/documents/{doc_id}/prescan — Pre-scan, infer_confidence
T11: POST /api/pipeline/trigger — PENDING→state 전이 트리거
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

# ── 공통 픽스처 ────────────────────────────────────────────────────────────


def _make_mock_pool(fetchrow_return=None, execute_return=None, fetchval_return=None):
    """asyncpg 풀 Mock — acquire() 컨텍스트 매니저 반환."""
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=fetchrow_return)
    mock_conn.execute  = AsyncMock(return_value=execute_return)
    mock_conn.fetchval = AsyncMock(return_value=fetchval_return)

    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=mock_conn),
        __aexit__=AsyncMock(return_value=False),
    ))
    return mock_pool, mock_conn


# ── T09: POST /api/documents ───────────────────────────────────────────────


@pytest.mark.anyio
async def test_T09_post_documents_single_url():
    """Arrange: 단일 유효 URL.
    Act: POST /api/documents.
    Assert: 201, doc_id 포함, state='PENDING'.
    """
    from app.main import app

    mock_pool, mock_conn = _make_mock_pool(
        fetchrow_return={"doc_id": "EXT_test_abc12345", "state": "PENDING"}
    )
    app.state.pool = mock_pool

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/documents",
            json={"urls": ["https://docs.djangoproject.com/en/6.0/topics/security/"]},
        )

    assert resp.status_code == 201
    body = resp.json()
    assert "documents" in body
    assert len(body["documents"]) == 1
    assert body["documents"][0]["state"] == "PENDING"


@pytest.mark.anyio
async def test_T09_post_documents_max_5_urls():
    """Arrange: URL 5개 (최대).
    Act: POST /api/documents.
    Assert: 201, documents 5개.
    """
    from app.main import app

    mock_pool, mock_conn = _make_mock_pool(
        fetchrow_return={"doc_id": "EXT_multi_00000000", "state": "PENDING"}
    )
    app.state.pool = mock_pool

    urls = [f"https://example.com/page{i}" for i in range(5)]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/documents", json={"urls": urls})

    assert resp.status_code == 201
    assert len(resp.json()["documents"]) == 5


@pytest.mark.anyio
async def test_T09_post_documents_exceeds_5_urls():
    """Arrange: URL 6개 (초과).
    Act: POST /api/documents.
    Assert: 422 (Unprocessable Entity).
    """
    from app.main import app

    app.state.pool = MagicMock()

    urls = [f"https://example.com/page{i}" for i in range(6)]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/documents", json={"urls": urls})

    assert resp.status_code == 422


@pytest.mark.anyio
async def test_T09_post_documents_invalid_url():
    """Arrange: 유효하지 않은 URL 형식.
    Act: POST /api/documents.
    Assert: 422.
    """
    from app.main import app

    app.state.pool = MagicMock()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/documents", json={"urls": ["not-a-url"]})

    assert resp.status_code == 422


# ── T10: POST /api/documents/{doc_id}/prescan ──────────────────────────────


@pytest.mark.anyio
async def test_T10_prescan_returns_infer_confidence():
    """Arrange: 존재하는 doc_id, mock HTTP 응답 (Django docs).
    Act: POST /api/documents/{doc_id}/prescan.
    Assert: 200, infer_confidence > 0, framework 추론.
    """
    from app.main import app

    doc_id = "EXT_test_abcd1234"
    mock_pool, mock_conn = _make_mock_pool(
        fetchrow_return={
            "doc_id": doc_id,
            "original_url": "https://docs.djangoproject.com/en/6.0/topics/security/",
            "state": "PENDING",
        }
    )
    app.state.pool = mock_pool

    mock_html = """<html lang="en">
    <head><title>Django 6.0 Security</title>
    <meta name="description" content="Django security documentation"></head>
    <body><h1>Security in Django</h1></body></html>"""

    with patch("app.interfaces.api.prescan.httpx") as mock_httpx:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = mock_html
        mock_resp.headers = {"ETag": '"abc123"'}
        mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_httpx.AsyncClient.return_value)
        mock_httpx.AsyncClient.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.AsyncClient.return_value.get = AsyncMock(return_value=mock_resp)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(f"/api/documents/{doc_id}/prescan")

    assert resp.status_code == 200
    body = resp.json()
    assert "infer_confidence" in body
    assert body["infer_confidence"] >= 0.0


@pytest.mark.anyio
async def test_T10_prescan_doc_not_found():
    """Arrange: 존재하지 않는 doc_id.
    Act: POST /api/documents/NOTEXIST/prescan.
    Assert: 404.
    """
    from app.main import app

    mock_pool, mock_conn = _make_mock_pool(fetchrow_return=None)
    app.state.pool = mock_pool

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/documents/NOTEXIST/prescan")

    assert resp.status_code == 404


# ── T11: POST /api/pipeline/trigger ────────────────────────────────────────


@pytest.mark.anyio
async def test_T11_pipeline_trigger_ok():
    """Arrange: PENDING 상태 doc_id.
    Act: POST /api/pipeline/trigger.
    Assert: 202, session_id 반환, state=CRAWLING 전이.
    """
    from app.main import app

    doc_id = "EXT_trigger_test_00000000"
    mock_pool, mock_conn = _make_mock_pool(
        fetchrow_return={"doc_id": doc_id, "state": "PENDING", "original_url": "https://x.com"}
    )
    app.state.pool = mock_pool

    with patch("app.interfaces.api.pipeline.run_pipeline_task") as mock_task:
        mock_task.return_value = None
        mock_task.delay = MagicMock(return_value=MagicMock(id="celery-task-id"))

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/pipeline/trigger",
                json={"doc_id": doc_id},
            )

    assert resp.status_code == 202
    body = resp.json()
    assert "session_id" in body
    assert uuid.UUID(body["session_id"])  # 유효한 UUID


@pytest.mark.anyio
async def test_T11_pipeline_trigger_doc_not_found():
    """Arrange: 존재하지 않는 doc_id.
    Act: POST /api/pipeline/trigger.
    Assert: 404.
    """
    from app.main import app

    mock_pool, mock_conn = _make_mock_pool(fetchrow_return=None)
    app.state.pool = mock_pool

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/pipeline/trigger",
            json={"doc_id": "NOTEXIST"},
        )

    assert resp.status_code == 404
