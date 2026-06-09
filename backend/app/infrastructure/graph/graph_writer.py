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

# concept_name이 기존 노드의 aliases 배열에 포함되어 있으면 해당 노드의 name 반환
_RESOLVE_ALIAS = """
MATCH (c:Concept) WHERE $concept_name IN c.aliases
RETURN c.name AS canonical LIMIT 1
"""


async def _resolve_canonical_name(session: neo4j.AsyncSession, concept_name: str) -> str:
    """concept_name이 다른 노드의 aliases에 있으면 그 노드의 name 반환, 없으면 원본 반환."""
    result = await session.run(_RESOLVE_ALIAS, concept_name=concept_name)
    record = await result.single()
    return record["canonical"] if record else concept_name


async def write_concept_node(
    concept: ConceptExtractionSchema,
    driver: neo4j.AsyncDriver,
) -> None:
    """Concept 노드 MERGE + 물리 다중 라벨 + 4종 관계 적재.

    멱등성: ON MATCH SET updated_at만 갱신 (노드 중복 없음).
    alias 수렴: concept_name이 기존 노드의 aliases에 있으면 해당 노드로 라우팅.
    """
    labels = [d.capitalize() for d in concept.domains]

    async with driver.session() as session:
        # 0. alias 수렴: concept_name이 기존 노드의 aliases에 등록돼 있으면 그 노드로 라우팅
        canonical_name = await _resolve_canonical_name(session, concept.concept_name)
        is_alias_redirect = canonical_name != concept.concept_name

        if not is_alias_redirect:
            # 1. Concept MERGE (신규 or 자기 자신)
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

        # 3. MITIGATED_BY → Mechanism  (mech is MechanismIn, not str)
        for mech in concept.mechanism:
            await session.run(
                "MATCH (c:Concept {name:$cn}) "
                "MERGE (m:Mechanism {name:$mn}) "
                "MERGE (c)-[:MITIGATED_BY]->(m)",
                cn=canonical_name, mn=mech.mechanism_name,
            )

        # 4. CAUSED_BY → RootCause
        if concept.root_cause:
            await session.run(
                "MATCH (c:Concept {name:$cn}) "
                "MERGE (r:RootCause {name:$rn}) "
                "MERGE (c)-[:CAUSED_BY]->(r)",
                cn=canonical_name, rn=concept.root_cause,
            )

        # 5. AFFECTS → Component
        for comp in concept.affected_components:
            await session.run(
                "MATCH (c:Concept {name:$cn}) "
                "MERGE (x:Component {name:$xn}) "
                "MERGE (c)-[:AFFECTS]->(x)",
                cn=canonical_name, xn=comp,
            )

        # 6. CONFIGURED_BY → ConfigProperty  (prop is PropertyIn, not dict)
        for prop in concept.config_properties:
            await session.run(
                "MATCH (c:Concept {name:$cn}) "
                "MERGE (p:ConfigProperty {key:$pk}) ON CREATE SET p.value=$pv "
                "MERGE (c)-[:CONFIGURED_BY]->(p)",
                cn=canonical_name,
                pk=prop.key,
                pv=prop.value,
            )

        # 7. HAS_EXAMPLE → CodeExample
        # lang + framework + lang_version + framework_version 4종 조합이 고유 키
        # ON CREATE SET: 동일 조합이 이미 있으면 code/description 덮어쓰지 않음
        for mech in concept.mechanism:
            for ex in mech.code_examples:
                if not ex.code:
                    continue
                await session.run(
                    "MATCH (m:Mechanism {name:$mn}) "
                    "MERGE (e:CodeExample {"
                    "  mechanism_name: $mn,"
                    "  lang: $lang,"
                    "  framework: $fw,"
                    "  lang_version: $lv,"
                    "  framework_version: $fv"
                    "}) "
                    "ON CREATE SET e.code = $code, e.description = $desc "
                    "MERGE (m)-[:HAS_EXAMPLE]->(e)",
                    mn=mech.mechanism_name,
                    lang=ex.lang,
                    fw=ex.framework,
                    lv=ex.lang_version,
                    fv=ex.framework_version,
                    code=ex.code,
                    desc=ex.description,
                )
