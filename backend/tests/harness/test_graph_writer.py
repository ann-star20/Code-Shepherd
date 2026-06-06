"""GraphWriter — APOC addLabels 통합 테스트 (Phase 2 SDD T_gw_01~05).

SDD 스펙:
  - MERGE (c:Concept {name}) 멱등성
  - apoc.create.addLabels → 물리 다중 라벨 (:Concept:security, :Concept:performance)
  - MITIGATED_BY / CAUSED_BY / AFFECTS 관계 생성
"""

import uuid
import pytest

from app.domain.models import ConceptExtractionSchema
from app.infrastructure.graph.graph_writer import write_concept_node


def _concept(name: str, domains: list[str], **kw) -> ConceptExtractionSchema:
    return ConceptExtractionSchema(
        concept_name=name,
        domains=domains,
        severity="HIGH",
        description_ko="테스트 개념",
        **kw,
    )


def _uid(base: str) -> str:
    return f"{base}_{uuid.uuid4().hex[:6]}"


async def _cleanup(driver, name: str) -> None:
    async with driver.session() as s:
        await s.run("MATCH (c:Concept {name:$n}) DETACH DELETE c", n=name)


# T_gw_01: MERGE 멱등성 — 2회 write → 노드 1개
@pytest.mark.anyio
async def test_gw_merge_idempotent(async_neo4j_driver):
    name = _uid("XSS")
    try:
        await write_concept_node(_concept(name, ["security"]), async_neo4j_driver)
        await write_concept_node(_concept(name, ["security"]), async_neo4j_driver)
        async with async_neo4j_driver.session() as s:
            r = await s.run("MATCH (c:Concept {name:$n}) RETURN count(c) AS cnt", n=name)
            assert (await r.single())["cnt"] == 1
    finally:
        await _cleanup(async_neo4j_driver, name)


# T_gw_02: security domain → :Concept:security 물리 라벨
@pytest.mark.anyio
async def test_gw_security_physical_label(async_neo4j_driver):
    name = _uid("XSS")
    try:
        await write_concept_node(_concept(name, ["security"]), async_neo4j_driver)
        async with async_neo4j_driver.session() as s:
            r = await s.run(
                "MATCH (c:Concept:security {name:$n}) RETURN c.name AS n", n=name
            )
            assert (await r.single()) is not None
    finally:
        await _cleanup(async_neo4j_driver, name)


# T_gw_03: 교차 도메인 → :Concept:security:performance 물리 라벨 누적
@pytest.mark.anyio
async def test_gw_cross_domain_labels(async_neo4j_driver):
    name = _uid("MemoryLeak")
    try:
        await write_concept_node(_concept(name, ["security", "performance"]), async_neo4j_driver)
        async with async_neo4j_driver.session() as s:
            r = await s.run("MATCH (c:Concept {name:$n}) RETURN labels(c) AS lbs", n=name)
            labels = set((await r.single())["lbs"])
        assert {"Concept", "security", "performance"}.issubset(labels)
        # 구버전 Tag/TAGGED_WITH 방식 사용 안 함
        async with async_neo4j_driver.session() as s:
            r = await s.run(
                "MATCH (c:Concept {name:$n})-[:TAGGED_WITH]->() RETURN count(*) AS cnt", n=name
            )
            assert (await r.single())["cnt"] == 0
    finally:
        await _cleanup(async_neo4j_driver, name)


# T_gw_04: security_mechanisms → MITIGATED_BY → SecurityMechanism
@pytest.mark.anyio
async def test_gw_mitigated_by(async_neo4j_driver):
    name = _uid("CSRF")
    concept = _concept(name, ["security"], security_mechanisms=["CSRFToken", "SameSiteCookie"])
    try:
        await write_concept_node(concept, async_neo4j_driver)
        async with async_neo4j_driver.session() as s:
            r = await s.run(
                "MATCH (c:Concept {name:$n})-[:MITIGATED_BY]->(m:SecurityMechanism) "
                "RETURN count(m) AS cnt",
                n=name,
            )
            assert (await r.single())["cnt"] == 2
    finally:
        await _cleanup(async_neo4j_driver, name)


# T_gw_05: root_cause → CAUSED_BY, affected_components → AFFECTS
@pytest.mark.anyio
async def test_gw_caused_by_affects(async_neo4j_driver):
    name = _uid("SQLi")
    concept = _concept(
        name, ["security"],
        root_cause="입력값 미검증",
        affected_components=["DB 레이어", "ORM"],
    )
    try:
        await write_concept_node(concept, async_neo4j_driver)
        async with async_neo4j_driver.session() as s:
            r1 = await s.run(
                "MATCH (c:Concept {name:$n})-[:CAUSED_BY]->(:RootCause) RETURN count(*) AS cnt",
                n=name,
            )
            r2 = await s.run(
                "MATCH (c:Concept {name:$n})-[:AFFECTS]->(:Component) RETURN count(*) AS cnt",
                n=name,
            )
            assert (await r1.single())["cnt"] == 1
            assert (await r2.single())["cnt"] == 2
    finally:
        await _cleanup(async_neo4j_driver, name)
