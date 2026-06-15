"""tests/test_neo4j_repo.py — Neo4jConceptRepo.get_topology 테스트."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from app.adapters.db.neo4j_repo import Neo4jConceptRepo
from app.domain.models import CodeExampleSchema, ConceptExtractionSchema, MechanismSchema


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


def _make_merge_driver() -> tuple[MagicMock, AsyncMock]:
    """merge_concept() 트랜잭션 흐름을 모사하는 driver/session/tx 모킹."""
    concept_result = AsyncMock()
    concept_result.single = AsyncMock(return_value={"name": "XSS"})

    tx = AsyncMock()
    tx.run = AsyncMock(return_value=concept_result)
    tx.commit = AsyncMock()
    tx.rollback = AsyncMock()

    session = AsyncMock()
    session.begin_transaction = AsyncMock(return_value=tx)

    session_cm = AsyncMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=False)

    driver = MagicMock()
    driver.session = MagicMock(return_value=session_cm)
    return driver, tx


def _concept(mechanism: list[MechanismSchema]) -> ConceptExtractionSchema:
    return ConceptExtractionSchema(
        concept_name="XSS",
        domains=["security"],
        aliases=["Cross-Site Scripting"],
        mechanism=mechanism,
    )


class TestMergeConcept:
    """merge_concept()/_merge_code_example() — 그래프 멱등성 + CodeExample 다형성."""

    async def test_commits_transaction_and_returns_concept_name(self):
        # Arrange
        driver, tx = _make_merge_driver()
        repo = Neo4jConceptRepo(driver, "neo4j")
        concept = _concept(mechanism=[])

        # Act
        result = await repo.merge_concept(concept)

        # Assert
        assert result == "XSS"
        tx.commit.assert_awaited_once()
        tx.rollback.assert_not_called()

    async def test_rolls_back_on_exception(self):
        # Arrange
        driver, tx = _make_merge_driver()
        tx.run = AsyncMock(side_effect=RuntimeError("neo4j down"))
        repo = Neo4jConceptRepo(driver, "neo4j")
        concept = _concept(mechanism=[])

        # Act / Assert
        try:
            await repo.merge_concept(concept)
            assert False, "RuntimeError가 발생해야 함"
        except RuntimeError:
            pass
        tx.rollback.assert_awaited_once()
        tx.commit.assert_not_called()

    async def test_same_lang_framework_combo_reuses_unq_id_idempotently(self):
        """동일 (lang, lang_version, framework, framework_version) 조합 재추출 → 동일 unq_id로 MERGE (멱등성)."""
        # Arrange
        driver, tx = _make_merge_driver()
        repo = Neo4jConceptRepo(driver, "neo4j")
        code_example = CodeExampleSchema(
            lang="python",
            lang_version="3.11",
            framework="django",
            framework_version="4.2",
            code="escape(user_input)",
            description="사용자 입력을 이스케이프 처리",
        )
        concept = _concept(
            mechanism=[
                MechanismSchema(mechanism_name="output_encoding", code_examples=[code_example])
            ]
        )

        # Act — 동일 데이터로 두 번 merge (재추출 시나리오)
        await repo.merge_concept(concept)
        await repo.merge_concept(concept)

        # Assert — CodeExample MERGE 호출은 항상 동일한 unq_id를 사용
        code_example_calls = [
            call for call in tx.run.await_args_list if call.kwargs.get("unq_id")
        ]
        unq_ids = {call.kwargs["unq_id"] for call in code_example_calls}
        assert unq_ids == {"output_encoding_python_3.11_django_4.2"}
        assert len(code_example_calls) == 2
        for call in code_example_calls:
            assert "MERGE (ce:CodeExample {unq_id: $unq_id})" in call.args[0]
            assert "ON CREATE SET" in call.args[0]
            assert "ON MATCH SET" in call.args[0]

    async def test_different_lang_framework_combo_appends_new_code_example_node(self):
        """언어/프레임워크 조합이 다르면 동일 Mechanism 아래 새로운 CodeExample 노드를 Append."""
        # Arrange
        driver, tx = _make_merge_driver()
        repo = Neo4jConceptRepo(driver, "neo4j")
        python_example = CodeExampleSchema(
            lang="python",
            lang_version="3.11",
            framework="django",
            framework_version="4.2",
            code="escape(user_input)",
            description="Django 템플릿 자동 이스케이프",
        )
        js_example = CodeExampleSchema(
            lang="javascript",
            lang_version="ES2022",
            framework="react",
            framework_version="18",
            code="<div>{userInput}</div>",
            description="React JSX 자동 이스케이프",
        )
        concept = _concept(
            mechanism=[
                MechanismSchema(
                    mechanism_name="output_encoding",
                    code_examples=[python_example, js_example],
                )
            ]
        )

        # Act
        await repo.merge_concept(concept)

        # Assert — 동일 Mechanism 아래 서로 다른 unq_id를 가진 두 CodeExample MERGE 호출
        code_example_calls = [
            call for call in tx.run.await_args_list if call.kwargs.get("unq_id")
        ]
        unq_ids = [call.kwargs["unq_id"] for call in code_example_calls]
        assert unq_ids == [
            "output_encoding_python_3.11_django_4.2",
            "output_encoding_javascript_ES2022_react_18",
        ]
        for call in code_example_calls:
            assert call.kwargs["mechanism_name"] == "output_encoding"

    async def test_code_example_on_match_refreshes_code_and_description(self):
        """동일 조합 재추출 시 ON MATCH로 code/description을 최신 내용으로 보강(Update)."""
        # Arrange
        driver, tx = _make_merge_driver()
        repo = Neo4jConceptRepo(driver, "neo4j")
        code_example = CodeExampleSchema(
            lang="python",
            lang_version="3.11",
            framework="django",
            framework_version="4.2",
            code="escape(user_input)  # v2",
            description="갱신된 설명",
        )
        concept = _concept(
            mechanism=[
                MechanismSchema(mechanism_name="output_encoding", code_examples=[code_example])
            ]
        )

        # Act
        await repo.merge_concept(concept)

        # Assert
        code_example_calls = [
            call for call in tx.run.await_args_list if call.kwargs.get("unq_id")
        ]
        call = code_example_calls[0]
        assert call.kwargs["code"] == "escape(user_input)  # v2"
        assert call.kwargs["description"] == "갱신된 설명"
        assert "ce.code        = $code" in call.args[0]
        assert "ce.description = $description" in call.args[0]
