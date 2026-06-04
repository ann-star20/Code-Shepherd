"""계약 테스트 — m3 엔드포인트."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

VERIFY_PAYLOAD = {
    "task_id": "t-002",
    "pr_id": "43",
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
async def test_verify_tests_contract(client):
    resp = await client.post("/verify/tests", json=VERIFY_PAYLOAD)
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_id"] == "t-002"
    assert data["agent"] == "test_verification"
    assert "issues" in data


@pytest.mark.asyncio
async def test_analyze_performance_contract(client):
    resp = await client.post("/analyze/performance", json=VERIFY_PAYLOAD)
    assert resp.status_code == 200
    assert resp.json()["agent"] == "performance"
