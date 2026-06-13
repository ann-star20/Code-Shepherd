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


def _make_driver(
    concept_records: list[dict],
    mechanism_records: list[dict],
    root_cause_records: list[dict],
    component_records: list[dict],
    code_example_records: list[dict],
    related_records: list[dict],
) -> MagicMock:
    session = AsyncMock()
    session.run = AsyncMock(
        side_effect=[
            _AsyncResult(concept_records),
            _AsyncResult(mechanism_records),
            _AsyncResult(root_cause_records),
            _AsyncResult(component_records),
            _AsyncResult(code_example_records),
            _AsyncResult(related_records),
        ]
    )

    session_cm = AsyncMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=False)

    driver = MagicMock()
    driver.session = MagicMock(return_value=session_cm)
    return driver


class TestGetTopology:
    async def test_returns_4layer_nodes_and_edges_from_neo4j(self):
        # Arrange
        concept_records = [
            {
                "name": "XSS",
                "domains": ["security"],
                "cwe_id": "CWE-79",
                "owasp_id": "A03:2021",
                "severity": "high",
                "description_ko": "설명",
                "aliases": ["Cross-Site Scripting"],
                "root_cause": "unsanitized_input",
            },
            {
                "name": "CSRF",
                "domains": ["security"],
                "cwe_id": "CWE-352",
                "owasp_id": None,
                "severity": "medium",
                "description_ko": None,
                "aliases": None,
                "root_cause": None,
            },
        ]
        mechanism_records = [{"concept_name": "XSS", "name": "output_encoding"}]
        root_cause_records = [{"concept_name": "XSS", "name": "unsanitized_input"}]
        component_records = [{"concept_name": "XSS", "name": "template_rendering_layer"}]
        code_example_records = [
            {
                "mechanism_name": "output_encoding",
                "unq_id": "output_encoding_python_3.11_django_4.2",
                "lang": "python",
                "lang_version": "3.11",
                "framework": "django",
                "framework_version": "4.2",
                "code": "escape(user_input)",
                "description": "사용자 입력을 이스케이프 처리",
            }
        ]
        related_records = [{"source": "XSS", "target": "CSRF", "type": "RELATED_TO"}]

        driver = _make_driver(
            concept_records,
            mechanism_records,
            root_cause_records,
            component_records,
            code_example_records,
            related_records,
        )
        repo = Neo4jConceptRepo(driver, "neo4j")

        # Act
        result = await repo.get_topology()

        # Assert
        nodes_by_id = {n["id"]: n for n in result["nodes"]}
        assert nodes_by_id["domain:security"] == {
            "id": "domain:security",
            "name": "security",
            "node_type": "Domain",
            "layer": "L1",
            "status": "COMMITTED",
        }
        assert nodes_by_id["XSS"]["node_type"] == "Concept"
        assert nodes_by_id["XSS"]["layer"] == "L2"
        assert nodes_by_id["XSS"]["root_cause"] == "unsanitized_input"
        assert nodes_by_id["CSRF"]["aliases"] == []
        assert nodes_by_id["mechanism:output_encoding"] == {
            "id": "mechanism:output_encoding",
            "name": "output_encoding",
            "node_type": "Mechanism",
            "layer": "L3",
            "status": "COMMITTED",
        }
        assert nodes_by_id["rootcause:unsanitized_input"]["node_type"] == "RootCause"
        assert nodes_by_id["component:template_rendering_layer"]["node_type"] == "Component"
        assert nodes_by_id["codeexample:output_encoding_python_3.11_django_4.2"] == {
            "id": "codeexample:output_encoding_python_3.11_django_4.2",
            "name": "output_encoding_python_3.11_django_4.2",
            "node_type": "CodeExample",
            "layer": "L4",
            "status": "COMMITTED",
            "lang": "python",
            "lang_version": "3.11",
            "framework": "django",
            "framework_version": "4.2",
            "code": "escape(user_input)",
            "description": "사용자 입력을 이스케이프 처리",
        }

        assert {"source": "domain:security", "target": "XSS", "type": "BELONGS_TO"} in result["edges"]
        assert {"source": "domain:security", "target": "CSRF", "type": "BELONGS_TO"} in result["edges"]
        assert {
            "source": "XSS",
            "target": "mechanism:output_encoding",
            "type": "MITIGATED_BY",
        } in result["edges"]
        assert {
            "source": "XSS",
            "target": "rootcause:unsanitized_input",
            "type": "CAUSED_BY",
        } in result["edges"]
        assert {
            "source": "XSS",
            "target": "component:template_rendering_layer",
            "type": "AFFECTS",
        } in result["edges"]
        assert {
            "source": "mechanism:output_encoding",
            "target": "codeexample:output_encoding_python_3.11_django_4.2",
            "type": "HAS_EXAMPLE",
        } in result["edges"]
        assert {"source": "XSS", "target": "CSRF", "type": "RELATED_TO"} in result["edges"]

    async def test_returns_empty_lists_for_empty_graph(self):
        # Arrange
        driver = _make_driver([], [], [], [], [], [])
        repo = Neo4jConceptRepo(driver, "neo4j")

        # Act
        result = await repo.get_topology()

        # Assert
        assert result == {"nodes": [], "edges": []}
