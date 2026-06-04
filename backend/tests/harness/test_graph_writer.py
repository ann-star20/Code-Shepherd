"""G8: GraphWriter — write_concept_node 통합 테스트."""

import uuid
import pytest

from app.domain.models import ConceptExtractionSchema, ConceptDomain
from app.infrastructure.graph.graph_writer import write_concept_node


# ── 테스트 데이터 팩토리 ──────────────────────────────────────────────────────

def _concept(name: str, domain: str = "security", aliases: list[str] | None = None) -> ConceptExtractionSchema:
    return ConceptExtractionSchema(
        concept_name=name,
        concept_domain=domain,
        severity="HIGH",
        description_ko="테스트 개념",
        cwe_id="CWE-79",
        aliases=aliases or [],
    )


def _uid(base: str) -> str:
    return f"{base}_{uuid.uuid4().hex[:6]}"


# ── T_gw_merge_idempotent ─────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_gw_merge_idempotent(async_neo4j_driver):
    """동일 concept를 2회 write → Concept 노드 1개만 존재."""
    name = _uid("XSS")
    concept = _concept(name)

    try:
        await write_concept_node(concept, async_neo4j_driver)
        await write_concept_node(concept, async_neo4j_driver)

        async with async_neo4j_driver.session() as session:
            result = await session.run(
                "MATCH (c:Concept {name: $name}) RETURN count(c) AS n", name=name
            )
            record = await result.single()
        assert record["n"] == 1
    finally:
        async with async_neo4j_driver.session() as session:
            await session.run("MATCH (c:Concept {name: $name}) DETACH DELETE c", name=name)


# ── T_gw_security_tag ─────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_gw_security_tag(async_neo4j_driver):
    """concept_domain='security' → Security 태그 연결."""
    name = _uid("XSS")
    concept = _concept(name, domain="security")

    try:
        await write_concept_node(concept, async_neo4j_driver)

        async with async_neo4j_driver.session() as session:
            result = await session.run(
                """MATCH (c:Concept {name: $name})-[:TAGGED_WITH]->(t:Tag {name: 'Security'})
                   RETURN count(t) AS n""",
                name=name,
            )
            record = await result.single()
        assert record["n"] == 1
    finally:
        async with async_neo4j_driver.session() as session:
            await session.run("MATCH (c:Concept {name: $name}) DETACH DELETE c", name=name)


# ── T_gw_both_tags ────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_gw_both_tags(async_neo4j_driver):
    """concept_domain='both' → Security + Performance 태그 각 1개."""
    name = _uid("MemoryLeak")
    concept = _concept(name, domain="both")

    try:
        await write_concept_node(concept, async_neo4j_driver)

        async with async_neo4j_driver.session() as session:
            result = await session.run(
                """MATCH (c:Concept {name: $name})-[:TAGGED_WITH]->(t:Tag)
                   RETURN t.name AS tag""",
                name=name,
            )
            tags = {r["tag"] async for r in result}

        assert "Security" in tags
        assert "Performance" in tags
        assert len(tags) == 2
    finally:
        async with async_neo4j_driver.session() as session:
            await session.run("MATCH (c:Concept {name: $name}) DETACH DELETE c", name=name)


# ── T_gw_aliases ──────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_gw_aliases(async_neo4j_driver):
    """aliases 속성이 Concept 노드에 저장된다."""
    name = _uid("XSS")
    alias = "Cross-Site Scripting"
    concept = _concept(name, aliases=[alias])

    try:
        await write_concept_node(concept, async_neo4j_driver)

        async with async_neo4j_driver.session() as session:
            result = await session.run(
                "MATCH (c:Concept {name: $name}) RETURN c.aliases AS aliases",
                name=name,
            )
            record = await result.single()
        assert alias in record["aliases"]
    finally:
        async with async_neo4j_driver.session() as session:
            await session.run("MATCH (c:Concept {name: $name}) DETACH DELETE c", name=name)
