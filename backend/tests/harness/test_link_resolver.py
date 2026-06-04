"""G10: LinkResolver — find_same_as_candidates + create_same_as_relation 통합 테스트."""

import uuid
import pytest

from app.usecases.link_resolver import find_same_as_candidates, create_same_as_relation


def _uid(base: str) -> str:
    return f"{base}_{uuid.uuid4().hex[:6]}"


async def _create_concept(session, name: str, aliases: list[str] = None) -> None:
    await session.run(
        "MERGE (c:Concept {name: $name}) SET c.aliases = $aliases",
        name=name, aliases=aliases or [],
    )


async def _cleanup(driver, *names: str) -> None:
    async with driver.session() as s:
        await s.run(
            "UNWIND $names AS n MATCH (c:Concept {name: n}) DETACH DELETE c",
            names=list(names),
        )


# ── T_resolver_finds_alias ────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_resolver_finds_alias(async_neo4j_driver):
    """XSS 노드에 alias 'Cross-Site Scripting' → 동일 alias로 탐색 시 XSS 반환."""
    xss_name = _uid("XSS")
    query_name = _uid("CrossSiteScripting")

    async with async_neo4j_driver.session() as s:
        await _create_concept(s, xss_name, aliases=["Cross-Site Scripting"])

    try:
        result = await find_same_as_candidates(
            query_name, ["Cross-Site Scripting"], async_neo4j_driver
        )
        assert xss_name in result
    finally:
        await _cleanup(async_neo4j_driver, xss_name)


# ── T_resolver_no_match ───────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_resolver_no_match(async_neo4j_driver):
    """관련 없는 노드만 존재 → 빈 리스트 반환."""
    unrelated = _uid("Unrelated")

    async with async_neo4j_driver.session() as s:
        await _create_concept(s, unrelated, aliases=["something else"])

    try:
        result = await find_same_as_candidates("Unknown", [], async_neo4j_driver)
        # 빈 aliases로 조회 → 매칭 없음
        assert result == []
    finally:
        await _cleanup(async_neo4j_driver, unrelated)


# ── T_resolver_creates_rel ────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_resolver_creates_rel(async_neo4j_driver):
    """두 Concept 노드 사이에 SAME_AS 관계 1개 생성."""
    name_a = _uid("XSS")
    name_b = _uid("Alt")

    async with async_neo4j_driver.session() as s:
        await _create_concept(s, name_a)
        await _create_concept(s, name_b)

    try:
        await create_same_as_relation(name_a, name_b, async_neo4j_driver)

        async with async_neo4j_driver.session() as s:
            result = await s.run(
                """MATCH (a:Concept {name: $a})-[r:SAME_AS]-(b:Concept {name: $b})
                   RETURN count(r) AS n""",
                a=name_a, b=name_b,
            )
            record = await result.single()
        assert record["n"] == 1
    finally:
        await _cleanup(async_neo4j_driver, name_a, name_b)
