"""Link Resolver Agent — aliases 기반 SAME_AS 관계 탐색 (PRD §규칙③).

동작:
  1. target concept의 aliases 배열과 교집합을 가진 다른 Concept 탐색
  2. MERGE (a)-[:SAME_AS]-(b) — 멱등 (무방향 관계)
  3. aliases 없거나 겹치는 개념 없으면 (0, 0) 반환
"""

import neo4j

_DELETE_STALE_SAME_AS = """
MATCH (t:Concept {name: $name})-[r:SAME_AS]-()
DELETE r
"""

_FIND_ALIAS_OVERLAPS = """
MATCH (target:Concept {name: $name})
MATCH (other:Concept)
WHERE other.name <> target.name
  AND (
    any(a IN target.aliases WHERE a IN other.aliases)
    OR target.name IN other.aliases
    OR other.name IN target.aliases
  )
RETURN other.name AS other_name
"""

_MERGE_SAME_AS = """
MATCH (a:Concept {name: $a_name})
MATCH (b:Concept {name: $b_name})
MERGE (a)-[:SAME_AS]-(b)
"""


async def resolve_links(
    concept_name: str,
    driver: neo4j.AsyncDriver,
) -> tuple[int, int]:
    """aliases 중복 탐색 후 SAME_AS 관계를 MERGE로 형성한다.

    이전 실행의 스테일 SAME_AS 엣지를 먼저 삭제한 후 재생성하여 멱등성 보장.
    concept 이름 자체가 상대방 aliases에 포함된 경우도 동의어로 인식.

    Returns:
        (same_as_count, related_count) — 현재 related_count는 항상 0.
    """
    same_as_count = 0

    async with driver.session() as session:
        await session.run(_DELETE_STALE_SAME_AS, name=concept_name)

        result = await session.run(_FIND_ALIAS_OVERLAPS, name=concept_name)
        matches = await result.data()

        for match in matches:
            await session.run(
                _MERGE_SAME_AS,
                a_name=concept_name,
                b_name=match["other_name"],
            )
            same_as_count += 1

    return same_as_count, 0
