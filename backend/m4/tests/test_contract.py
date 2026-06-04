"""계약 테스트 — m4 엔드포인트."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

EVALUATE_PAYLOAD = {
    "task_id": "t-003",
    "pr_id": "44",
}
CURRICULUM_PAYLOAD = {
    "task_id": "t-004",
    "developer": {
        "id": "dev-1",
        "skill_level": "junior",
        "tech_stack": ["python"],
    },
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
async def test_evaluate_contract(client):
    resp = await client.post("/evaluate", json=EVALUATE_PAYLOAD)
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_id"] == "t-003"
    assert data["pr_id"] == "44"
    assert data["verdict"] in ("lgtm", "rework", "escalate")
    assert "comment_body" in data


@pytest.mark.asyncio
async def test_curriculum_contract(client):
    resp = await client.post("/curriculum", json=CURRICULUM_PAYLOAD)
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_id"] == "t-004"
    assert "roadmap" in data
