"""G10: LinkResolver — SAME_AS 후보 탐색 + 관계 생성."""

import neo4j


async def find_same_as_candidates(
    concept_name: str,
    aliases: list[str],
    driver: neo4j.AsyncDriver,
) -> list[str]:
    """aliases와 겹치는 이름 또는 aliases를 가진 Concept 이름 목록을 반환한다."""
    if not aliases:
        return []

    cypher = """
    MATCH (c:Concept)
    WHERE (c.name IN $aliases OR any(a IN c.aliases WHERE a IN $aliases))
      AND c.name <> $concept_name
    RETURN c.name AS name
    """
    async with driver.session() as session:
        result = await session.run(cypher, concept_name=concept_name, aliases=aliases)
        return [r["name"] async for r in result]


async def create_same_as_relation(
    name_a: str,
    name_b: str,
    driver: neo4j.AsyncDriver,
) -> None:
    """두 Concept 사이에 SAME_AS 관계를 멱등하게 생성한다."""
    cypher = """
    MATCH (a:Concept {name: $a}), (b:Concept {name: $b})
    MERGE (a)-[:SAME_AS]->(b)
    """
    async with driver.session() as session:
        await session.run(cypher, a=name_a, b=name_b)
