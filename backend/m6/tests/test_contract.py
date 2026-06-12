"""M6 Output Contract 기본 검증."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["service"] == "m6-knowledge-graph"


def test_ingest_stub_returns_202():
    res = client.post("/graph/ingest", json={"url": "https://example.com/doc"})
    assert res.status_code == 202
    data = res.json()
    assert "task_id" in data
    assert data["status"] == "pending"


def test_query_stub_returns_empty_graph():
    res = client.post("/graph/query", json={"query": "python", "limit": 10})
    assert res.status_code == 200
    data = res.json()
    assert data["nodes"] == []
    assert data["edges"] == []
    assert data["total"] == 0
