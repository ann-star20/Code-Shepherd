"""GraphWriter — Concept MERGE + APOC addLabels (PRD §3.3.4 + task1_multi_domain §5).

Tag Node / DOMAIN_TAG_MAP / "both" 완전 폐기.
domains: list[str] → [d.capitalize() for d in domains] → apoc.create.addLabels.
"""

import neo4j

from app.domain.models import ConceptExtractionSchema

_MERGE_CONCEPT = """
MERGE (c:Concept {name: $name})
ON CREATE SET
  c.aliases        = $aliases,
  c.cwe_id         = $cwe_id,
  c.description_ko = $description_ko,
  c.severity       = $severity,
  c.domains        = $domains,
  c.created_at     = timestamp()
ON MATCH SET
  c.updated_at     = timestamp(),
  c.domains        = apoc.coll.toSet(c.domains + $domains)
"""

_ADD_LABELS = """
MATCH (c:Concept {name: $name})
CALL apoc.create.addLabels(c, $labels) YIELD node
RETURN node.name AS name
"""


async def write_concept_node(
    concept: ConceptExtractionSchema,
    driver: neo4j.AsyncDriver,
) -> None:
    """Concept 노드 MERGE + 물리 다중 라벨 + 4종 관계 적재.

    멱등성: ON MATCH SET updated_at만 갱신 (노드 중복 없음).
    """
    labels = [d.capitalize() for d in concept.domains]

    async with driver.session() as session:
        # 1. Concept MERGE
        await session.run(
            _MERGE_CONCEPT,
            name=concept.concept_name,
            aliases=concept.aliases,
            cwe_id=concept.cwe_id,
            description_ko=concept.description_ko,
            severity=concept.severity,
            domains=concept.domains,
        )

        # 2. APOC 물리 다중 라벨 누적 (기존 라벨 제거 없음)
        await session.run(_ADD_LABELS, name=concept.concept_name, labels=labels)

        # 3. MITIGATED_BY → SecurityMechanism  (mech is MechanismIn, not str)
        for mech in concept.security_mechanism:
            await session.run(
                "MATCH (c:Concept {name:$cn}) "
                "MERGE (m:SecurityMechanism {name:$mn}) "
                "MERGE (c)-[:MITIGATED_BY]->(m)",
                cn=concept.concept_name, mn=mech.mechanism_name,
            )

        # 4. CAUSED_BY → RootCause
        if concept.root_cause:
            await session.run(
                "MATCH (c:Concept {name:$cn}) "
                "MERGE (r:RootCause {name:$rn}) "
                "MERGE (c)-[:CAUSED_BY]->(r)",
                cn=concept.concept_name, rn=concept.root_cause,
            )

        # 5. AFFECTS → Component
        for comp in concept.affected_components:
            await session.run(
                "MATCH (c:Concept {name:$cn}) "
                "MERGE (x:Component {name:$xn}) "
                "MERGE (c)-[:AFFECTS]->(x)",
                cn=concept.concept_name, xn=comp,
            )

        # 6. CONFIGURED_BY → ConfigProperty  (prop is PropertyIn, not dict)
        for prop in concept.config_properties:
            await session.run(
                "MATCH (c:Concept {name:$cn}) "
                "MERGE (p:ConfigProperty {key:$pk}) ON CREATE SET p.value=$pv "
                "MERGE (c)-[:CONFIGURED_BY]->(p)",
                cn=concept.concept_name,
                pk=prop.key,
                pv=prop.value,
            )

        # 7. HAS_EXAMPLE → CodeExample  (examples live inside MechanismIn after model_validator)
        for mech in concept.security_mechanism:
            for ex in mech.code_examples:
                if not ex.code:
                    continue
                await session.run(
                    "MATCH (c:Concept {name:$cn}) "
                    "MERGE (e:CodeExample {concept_name:$cn, lang:$lang, framework:$fw}) "
                    "SET e.code = $code "
                    "MERGE (c)-[:HAS_EXAMPLE]->(e)",
                    cn=concept.concept_name,
                    lang=ex.lang,
                    fw=ex.framework,
                    code=ex.code,
                )
