"""계약 테스트 — m5 엔드포인트."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

EXTRACT_PAYLOAD = {
    "task_id": "t-m5-001",
    "doc_id": "doc-abc-123",
    "source": "upload",
}

YOUTUBE_PAYLOAD = {
    "task_id": "t-m5-002",
    "keywords": ["fastapi", "neo4j"],
    "doc_id": "doc-abc-123",
}


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["service"] == "m5-graph-youtube"


@pytest.mark.asyncio
async def test_extract_contract(client):
    resp = await client.post("/extract", json=EXTRACT_PAYLOAD)
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_id"] == "t-m5-001"
    assert data["doc_id"] == "doc-abc-123"
    assert data["status"] in ("accepted", "processing", "done", "failed")


@pytest.mark.asyncio
async def test_youtube_recommend_contract(client):
    resp = await client.post("/youtube/recommend", json=YOUTUBE_PAYLOAD)
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_id"] == "t-m5-002"
    assert "videos" in data
