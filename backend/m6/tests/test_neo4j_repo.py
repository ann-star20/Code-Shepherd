"""tests/test_neo4j_repo.py — Neo4jConceptRepo.get_topology 테스트."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from app.adapters.db.neo4j_repo import Neo4jConceptRepo


class _AsyncResult:
    """neo4j AsyncResult의 `async for record in result` 동작을 모사."""

    def __init__(self, records: list[dict]) -> None:
        self._records = records

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for record in self._records:
            yield record


def _make_driver(node_records: list[dict], edge_records: list[dict]) -> MagicMock:
    session = AsyncMock()
    session.run = AsyncMock(side_effect=[_AsyncResult(node_records), _AsyncResult(edge_records)])

    session_cm = AsyncMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=False)

    driver = MagicMock()
    driver.session = MagicMock(return_value=session_cm)
    return driver


class TestGetTopology:
    async def test_returns_nodes_and_edges_from_neo4j(self):
        # Arrange
        node_records = [
            {
                "name": "XSS",
                "domains": ["security"],
                "cwe_id": "CWE-79",
                "owasp_id": "A03:2021",
                "severity": "high",
                "description_ko": "설명",
                "aliases": ["Cross-Site Scripting"],
            },
            {
                "name": "CSRF",
                "domains": ["security"],
                "cwe_id": "CWE-352",
                "owasp_id": None,
                "severity": "medium",
                "description_ko": None,
                "aliases": None,
            },
        ]
        edge_records = [{"source": "XSS", "target": "CSRF", "type": "RELATED_TO"}]
        driver = _make_driver(node_records, edge_records)
        repo = Neo4jConceptRepo(driver, "neo4j")

        # Act
        result = await repo.get_topology()

        # Assert
        assert result["nodes"][0] == {
            "id": "XSS",
            "name": "XSS",
            "status": "COMMITTED",
            "domains": ["security"],
            "cwe_id": "CWE-79",
            "owasp_id": "A03:2021",
            "severity": "high",
            "description_ko": "설명",
            "aliases": ["Cross-Site Scripting"],
        }
        assert result["nodes"][1]["aliases"] == []
        assert result["edges"] == [{"source": "XSS", "target": "CSRF", "type": "RELATED_TO"}]

    async def test_returns_empty_lists_for_empty_graph(self):
        # Arrange
        driver = _make_driver([], [])
        repo = Neo4jConceptRepo(driver, "neo4j")

        # Act
        result = await repo.get_topology()

        # Assert
        assert result == {"nodes": [], "edges": []}
