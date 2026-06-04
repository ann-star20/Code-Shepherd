"""계약 테스트 — m2 엔드포인트."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

ANALYZE_PAYLOAD = {
    "task_id": "t-001",
    "pr_id": "42",
    "pr_diff": "diff --git ...",
}


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_analyze_static_contract(client):
    resp = await client.post("/analyze/static", json=ANALYZE_PAYLOAD)
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_id"] == "t-001"
    assert data["agent"] == "static_analysis"
    assert "issues" in data
    assert "summary" in data


@pytest.mark.asyncio
async def test_analyze_security_contract(client):
    resp = await client.post("/analyze/security", json=ANALYZE_PAYLOAD)
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent"] == "security_scan"
