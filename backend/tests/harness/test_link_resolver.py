"""G12: Link Resolver Agent 통합 테스트 — SAME_AS 관계 탐색.

SDD 스펙:
  - aliases 배열 교집합 존재 시 MERGE (a)-[:SAME_AS]-(b)
  - MERGE → 멱등성 (2회 실행 시 관계 1개)
  - aliases 없는 concept → (0, 0), 예외 없음

T_lr_01: aliases 중복 → SAME_AS 1개 생성
T_lr_02: aliases 비중복 → SAME_AS 0개
T_lr_03: 동일 호출 2회 → SAME_AS 멱등 (1개 유지)
T_lr_04: aliases 없는 concept → (0, 0) 반환, 예외 없음
"""

import uuid
import pytest

from app.infrastructure.graph.link_resolver import resolve_links


def _uid(base: str) -> str:
    return f"{base}_{uuid.uuid4().hex[:6]}"


async def _create_concept(session, name: str, aliases: list[str]) -> None:
    await session.run(
        "MERGE (c:Concept {name: $name}) "
        "ON CREATE SET c.aliases=$aliases, c.created_at=timestamp() "
        "ON MATCH SET c.aliases=$aliases",
        name=name,
        aliases=aliases,
    )


async def _cleanup(driver, *names: str) -> None:
    async with driver.session() as s:
        await s.run(
            "UNWIND $names AS n MATCH (c:Concept {name:n}) DETACH DELETE c",
            names=list(names),
        )


async def _count_same_as(driver, a: str, b: str) -> int:
    async with driver.session() as s:
        result = await s.run(
            "MATCH (a:Concept {name:$a})-[:SAME_AS]-(b:Concept {name:$b}) RETURN count(*) AS n",
            a=a,
            b=b,
        )
        record = await result.single()
        return record["n"]


# ── T_lr_01 ───────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_lr_01_alias_overlap_creates_same_as(async_neo4j_driver):
    """Arrange: XSS와 CSS가 alias 'Cross-Site Scripting' 공유.
    Act: resolve_links(XSS, driver).
    Assert: SAME_AS 관계 1개, same_as_count == 1.
    """
    a = _uid("XSS")
    b = _uid("CSS")
    shared_alias = "Cross-Site Scripting"

    async with async_neo4j_driver.session() as s:
        await _create_concept(s, a, [shared_alias, "크로스 사이트 스크립팅"])
        await _create_concept(s, b, [shared_alias])

    try:
        same_as_count, _ = await resolve_links(a, async_neo4j_driver)
        assert same_as_count == 1, f"SAME_AS 관계가 {same_as_count}개 — 1개여야 함"
        assert await _count_same_as(async_neo4j_driver, a, b) == 1
    finally:
        await _cleanup(async_neo4j_driver, a, b)


# ── T_lr_02 ───────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_lr_02_no_alias_overlap_no_same_as(async_neo4j_driver):
    """Arrange: XSS와 SQLi — aliases 공유 없음.
    Act: resolve_links(XSS, driver).
    Assert: SAME_AS 0개, same_as_count == 0.
    """
    a = _uid("XSS")
    b = _uid("SQLi")

    async with async_neo4j_driver.session() as s:
        await _create_concept(s, a, ["Cross-Site Scripting"])
        await _create_concept(s, b, ["SQL Injection", "SQL 인젝션"])

    try:
        same_as_count, _ = await resolve_links(a, async_neo4j_driver)
        assert same_as_count == 0
        assert await _count_same_as(async_neo4j_driver, a, b) == 0
    finally:
        await _cleanup(async_neo4j_driver, a, b)


# ── T_lr_03 ───────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_lr_03_idempotent_same_as(async_neo4j_driver):
    """Arrange: aliases 공유 개념 쌍.
    Act: resolve_links 2회 실행.
    Assert: SAME_AS 관계 1개 유지 (MERGE 멱등성).
    """
    a = _uid("CSRF")
    b = _uid("XSRF")
    shared_alias = "Cross-Site Request Forgery"

    async with async_neo4j_driver.session() as s:
        await _create_concept(s, a, [shared_alias])
        await _create_concept(s, b, [shared_alias, "사이트 간 요청 위조"])

    try:
        await resolve_links(a, async_neo4j_driver)
        await resolve_links(a, async_neo4j_driver)  # 2회 실행
        assert await _count_same_as(async_neo4j_driver, a, b) == 1
    finally:
        await _cleanup(async_neo4j_driver, a, b)


# ── T_lr_04 ───────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_lr_04_empty_aliases_returns_zero(async_neo4j_driver):
    """Arrange: aliases 빈 concept.
    Act: resolve_links(concept, driver).
    Assert: (0, 0) 반환, 예외 없음.
    """
    name = _uid("EmptyConcept")

    async with async_neo4j_driver.session() as s:
        await _create_concept(s, name, [])

    try:
        result = await resolve_links(name, async_neo4j_driver)
        assert result == (0, 0)
    finally:
        await _cleanup(async_neo4j_driver, name)
