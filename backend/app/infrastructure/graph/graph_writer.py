"""G8: GraphWriter — Concept 노드 MERGE + TAGGED_WITH 관계."""

import neo4j

from app.domain.models import ConceptExtractionSchema

DOMAIN_TAG_MAP: dict[str, list[str]] = {
    "security":    ["Security"],
    "performance": ["Performance"],
    "both":        ["Security", "Performance"],
}

_CYPHER = """
MERGE (c:Concept {name: $name})
ON CREATE SET c.aliases      = $aliases,
              c.cwe_id        = $cwe_id,
              c.description_ko = $description_ko,
              c.created_at    = datetime()
ON MATCH  SET c.updated_at   = datetime()
WITH c
UNWIND $tags AS tag_name
  MERGE (t:Tag {name: tag_name})
  MERGE (c)-[:TAGGED_WITH]->(t)
"""


async def write_concept_node(
    concept: ConceptExtractionSchema,
    driver: neo4j.AsyncDriver,
) -> None:
    tags = DOMAIN_TAG_MAP[concept.concept_domain.value]
    async with driver.session() as session:
        await session.run(
            _CYPHER,
            name=concept.concept_name,
            aliases=concept.aliases,
            cwe_id=concept.cwe_id,
            description_ko=concept.description_ko,
            tags=tags,
        )
