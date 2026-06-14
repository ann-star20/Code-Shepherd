"""M6 Output Contract 기본 검증."""

import json
import uuid
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


@patch("app.api.routes.Neo4jConceptRepo")
@patch("app.api.routes.get_driver")
@patch("app.api.routes.get_database")
def test_topology_without_session_id_does_not_query_staging(
    mock_get_database, mock_get_driver, mock_repo_cls
):
    # Arrange
    mock_repo = AsyncMock()
    mock_repo.get_topology = AsyncMock(return_value={
        "nodes": [{"id": "XSS", "name": "XSS", "status": "COMMITTED", "domains": ["security"]}],
        "edges": [],
    })
    mock_repo_cls.return_value = mock_repo

    # Act
    res = client.get("/graph/topology")

    # Assert
    assert res.status_code == 200
    data = res.json()
    assert len(data["nodes"]) == 1
    assert all(not n.get("is_staging") for n in data["nodes"])


@patch("app.api.routes.asyncpg.connect", new_callable=AsyncMock)
@patch("app.api.routes.Neo4jConceptRepo")
@patch("app.api.routes.get_driver")
@patch("app.api.routes.get_database")
def test_topology_with_session_id_includes_draft_staging_nodes(
    mock_get_database, mock_get_driver, mock_repo_cls, mock_connect
):
    # Arrange
    mock_repo = AsyncMock()
    mock_repo.get_topology = AsyncMock(return_value={
        "nodes": [{"id": "XSS", "name": "XSS", "status": "COMMITTED", "domains": ["security"]}],
        "edges": [{"source": "XSS", "target": "CSRF", "type": "RELATED_TO"}],
    })
    mock_repo_cls.return_value = mock_repo

    staging_id = str(uuid.uuid4())
    draft_concept = {
        "concept_name": "Insecure Deserialization",
        "domains": ["security"],
        "description_ko": "신규 초안 개념",
        "aliases": [],
        "mechanism": [],
        "cwe_id": "CWE-502",
        "owasp_id": "A08:2021",
        "severity": "high",
    }
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[
        {
            "staging_id": staging_id,
            "concept_json": json.dumps(draft_concept),
            "infer_action": "NEW",
            "infer_confidence": 0.91,
            "target_concept_name": None,
        }
    ])
    conn.close = AsyncMock()
    mock_connect.return_value = conn
    session_id = str(uuid.uuid4())

    # Act
    res = client.get(f"/graph/topology?session_id={session_id}")

    # Assert
    assert res.status_code == 200
    data = res.json()
    assert data["edges"] == [{"source": "XSS", "target": "CSRF", "type": "RELATED_TO"}]
    nodes_by_id = {n["id"]: n for n in data["nodes"]}
    assert "XSS" in nodes_by_id
    draft_node = nodes_by_id[f"draft:{staging_id}"]
    assert draft_node["name"] == "Insecure Deserialization"
    assert draft_node["status"] == "DRAFT"
    assert draft_node["is_staging"] is True
    assert draft_node["is_new"] is True
    assert draft_node["layer"] == "L2"
    assert draft_node["node_type"] == "Concept"
