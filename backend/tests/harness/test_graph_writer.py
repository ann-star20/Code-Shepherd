"""GraphWriter — APOC addLabels 통합 테스트 (Phase 2 SDD T_gw_01~07).

SDD 스펙:
  - MERGE (c:Concept {name}) 멱등성
  - apoc.create.addLabels → 물리 다중 라벨 (:Concept:security, :Concept:performance)
  - MITIGATED_BY / CAUSED_BY / AFFECTS 관계 생성
  - alias 수렴: concept_name이 기존 노드 aliases에 있으면 해당 노드로 라우팅
  - CodeExample 4종 키(lang+framework+lang_version+framework_version) 멱등성
"""

import uuid
import pytest

from app.domain.models import CodeExampleIn, ConceptExtractionSchema, MechanismIn
from app.infrastructure.graph.graph_writer import write_concept_node


def _concept(name: str, domains: list[str], **kw) -> ConceptExtractionSchema:
    return ConceptExtractionSchema(
        concept_name=name,
        domains=domains,
        severity="high",
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


# T_gw_04: mechanism → MITIGATED_BY → Mechanism
@pytest.mark.anyio
async def test_gw_mitigated_by(async_neo4j_driver):
    name = _uid("CSRF")
    concept = _concept(name, ["security"], mechanism=["CSRFToken", "SameSiteCookie"])
    try:
        await write_concept_node(concept, async_neo4j_driver)
        async with async_neo4j_driver.session() as s:
            r = await s.run(
                "MATCH (c:Concept {name:$n})-[:MITIGATED_BY]->(m:Mechanism) "
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


# T_gw_06: alias 수렴 — concept_name이 기존 노드의 aliases에 있으면 그 노드로 라우팅, 신규 노드 미생성
@pytest.mark.anyio
async def test_gw_alias_redirect(async_neo4j_driver):
    canonical = _uid("CSRF")
    alias_name = "CrossSiteRequestForgery"
    mech_name = "csrf_token_check"

    # canonical 노드를 aliases 포함하여 먼저 적재
    canonical_concept = _concept(
        canonical, ["security"],
        aliases=[alias_name, "XSRF"],
        mechanism=[mech_name],
    )
    try:
        await write_concept_node(canonical_concept, async_neo4j_driver)

        # alias 이름으로 다시 적재 시도 → canonical 노드로 라우팅되어야 함
        alias_concept = _concept(
            alias_name, ["security"],
            mechanism=[mech_name],
        )
        await write_concept_node(alias_concept, async_neo4j_driver)

        async with async_neo4j_driver.session() as s:
            # alias_name으로 생성된 독립 노드가 없어야 함
            r_new = await s.run(
                "MATCH (c:Concept {name:$n}) RETURN count(c) AS cnt", n=alias_name
            )
            assert (await r_new.single())["cnt"] == 0

            # canonical 노드에 mechanism 관계가 연결돼 있어야 함
            r_mech = await s.run(
                "MATCH (c:Concept {name:$cn})-[:MITIGATED_BY]->(m:Mechanism {name:$mn}) "
                "RETURN count(m) AS cnt",
                cn=canonical, mn=mech_name,
            )
            assert (await r_mech.single())["cnt"] == 1
    finally:
        await _cleanup(async_neo4j_driver, canonical)


# T_gw_07: CodeExample 4종 키 멱등성
#   동일 (lang, framework, lang_version, framework_version) → 1개
#   다른 framework_version → 별도 노드
@pytest.mark.anyio
async def test_gw_code_example_version_dedup(async_neo4j_driver):
    name = _uid("XSS")
    mech = MechanismIn(
        mechanism_name="output_encoding",
        code_examples=[
            CodeExampleIn(lang="python", framework="Django", lang_version="3.11", framework_version="4.2", code="# v1"),
            CodeExampleIn(lang="python", framework="Django", lang_version="3.11", framework_version="4.2", code="# duplicate"),
            CodeExampleIn(lang="python", framework="Django", lang_version="3.11", framework_version="3.2", code="# v2"),
        ],
    )
    concept = _concept(name, ["security"], mechanism=[mech])
    try:
        await write_concept_node(concept, async_neo4j_driver)
        async with async_neo4j_driver.session() as s:
            r = await s.run(
                "MATCH (m:Mechanism {name:'output_encoding'})-[:HAS_EXAMPLE]->(e:CodeExample) "
                "RETURN count(e) AS cnt"
            )
            # 4.2 버전 1개 + 3.2 버전 1개 = 2개 (중복 제거)
            assert (await r.single())["cnt"] == 2
    finally:
        await _cleanup(async_neo4j_driver, name)
        async with async_neo4j_driver.session() as s:
            await s.run("MATCH (m:Mechanism {name:'output_encoding'}) DETACH DELETE m")
