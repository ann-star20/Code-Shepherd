"""M6 Output Contract 기본 검증."""

from unittest.mock import AsyncMock, patch

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


@patch("app.api.routes.Neo4jConceptRepo")
@patch("app.api.routes.get_driver")
@patch("app.api.routes.get_database")
def test_topology_returns_nodes_and_edges(mock_get_database, mock_get_driver, mock_repo_cls):
    # Arrange
    mock_repo = AsyncMock()
    mock_repo.get_topology = AsyncMock(return_value={
        "nodes": [{"id": "XSS", "name": "XSS", "status": "COMMITTED", "domains": ["security"]}],
        "edges": [{"source": "XSS", "target": "CSRF", "type": "RELATED_TO"}],
    })
    mock_repo_cls.return_value = mock_repo

    # Act
    res = client.get("/graph/topology")

    # Assert
    assert res.status_code == 200
    data = res.json()
    assert data["nodes"][0]["id"] == "XSS"
    assert data["edges"][0] == {"source": "XSS", "target": "CSRF", "type": "RELATED_TO"}
