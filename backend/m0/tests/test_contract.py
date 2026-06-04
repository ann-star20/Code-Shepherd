"""계약 테스트 — m0 엔드포인트가 계약 DTO로 200 반환."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_ingest_contract(client):
    """POST /ingest: 계약 DTO 수신 → 계약 형태로 200 반환."""
    payload = {
        "task_id": "task-001",
        "source": "upload",
        "doc_id": "doc-abc",
        "trace_id": "trace-xyz",
    }
    resp = await client.post("/ingest", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    # 계약 필드 확인
    assert data["task_id"] == "task-001"
    assert "status" in data
    assert "message" in data


@pytest.mark.asyncio
async def test_ingest_requires_task_id(client):
    """task_id 없으면 422."""
    resp = await client.post("/ingest", json={"doc_id": "doc-abc", "source": "upload"})
    assert resp.status_code == 422
