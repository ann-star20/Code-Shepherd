"""Neo4j 읽기 전용 쿼리 — 유튜브 추천용 메타데이터 조회."""

from __future__ import annotations

from pydantic import BaseModel

from app.neo4j_client import get_driver, get_database


# ── Response 스키마 ──────────────────────────────────────────────────────────

class ConceptOverview(BaseModel):
    concept_name: str
    severity: str | None = None
    mechanism_names: list[str] = []
    domain_names: list[str] = []


class GraphOverviewResponse(BaseModel):
    concepts: list[ConceptOverview]


class CodeExampleMeta(BaseModel):
    unq_id: str
    lang: str | None = None
    framework: str | None = None


class MechanismMeta(BaseModel):
    mechanism_name: str
    code_examples: list[CodeExampleMeta] = []


class ConceptGraphResponse(BaseModel):
    concept_name: str
    concept_desc: str | None = None
    cwe_id: str | None = None
    owasp_id: str | None = None
    severity: str | None = None
    affected_components: list[str] = []
    parent_domains: list[str] = []
    related_concepts: list[str] = []
    mechanisms: list[MechanismMeta] = []


class MechanismGraphResponse(BaseModel):
    mechanism_name: str
    concept_name: str
    code_examples: list[CodeExampleMeta] = []


# ── Cypher ───────────────────────────────────────────────────────────────────

_OVERVIEW_QUERY = """
MATCH (c:Concept)
OPTIONAL MATCH (c)-[:MITIGATED_BY]->(m:Mechanism)
RETURN
  c.name     AS concept_name,
  c.severity AS severity,
  c.domains  AS domain_names,
  collect(DISTINCT m.name) AS mechanism_names
ORDER BY c.name
"""

_CONCEPT_QUERY = """
MATCH (c:Concept)
WHERE toLower(c.name) = toLower($keyword)

OPTIONAL MATCH (c)-[]->(parent)
WHERE any(label IN labels(parent) WHERE label IN ['Domain', 'Classification'])

OPTIONAL MATCH (related:Concept)-[]->(parent)
WHERE related <> c

OPTIONAL MATCH (c)-[]->(m:Mechanism)
OPTIONAL MATCH (m)-[]->(ce:CodeExample)

RETURN
  c.name               AS concept_name,
  c.description_ko     AS concept_desc,
  c.cwe_id             AS cwe_id,
  c.owasp_id           AS owasp_id,
  c.severity           AS severity,
  c.affected_components AS affected_components,
  collect(DISTINCT parent.name)  AS parent_domains,
  collect(DISTINCT related.name) AS related_concepts,
  collect(DISTINCT {
    mechanism_name: m.name,
    unq_id:    ce.unq_id,
    lang:      ce.lang,
    framework: ce.framework
  }) AS mech_ce_pairs
"""

_MECHANISM_QUERY = """
MATCH (c:Concept)-[]->(m:Mechanism)
WHERE toLower(m.name) = toLower($mechanism_name)
OPTIONAL MATCH (m)-[]->(ce:CodeExample)
RETURN
  c.name AS concept_name,
  m.name AS mechanism_name,
  collect(DISTINCT {
    unq_id:    ce.unq_id,
    lang:      ce.lang,
    framework: ce.framework
  }) AS code_examples
LIMIT 1
"""


# ── 쿼리 함수 ────────────────────────────────────────────────────────────────

async def fetch_overview() -> GraphOverviewResponse:
    driver = get_driver()
    db = get_database()

    async with driver.session(database=db) as session:
        result = await session.run(_OVERVIEW_QUERY)
        records = await result.data()

    concepts = [
        ConceptOverview(
            concept_name=r["concept_name"],
            severity=r.get("severity"),
            mechanism_names=[n for n in (r.get("mechanism_names") or []) if n],
            domain_names=[n for n in (r.get("domain_names") or []) if n],
        )
        for r in records
        if r.get("concept_name")
    ]
    return GraphOverviewResponse(concepts=concepts)


async def fetch_concept(keyword: str) -> ConceptGraphResponse | None:
    driver = get_driver()
    db = get_database()

    async with driver.session(database=db) as session:
        result = await session.run(_CONCEPT_QUERY, keyword=keyword)
        record = await result.single()

    if record is None:
        return None

    # (mechanism_name → [CodeExampleMeta]) 재구성
    mech_map: dict[str, list[CodeExampleMeta]] = {}
    for pair in record["mech_ce_pairs"]:
        mech_name = pair.get("mechanism_name")
        if not mech_name:
            continue
        mech_map.setdefault(mech_name, [])
        if pair.get("unq_id"):
            mech_map[mech_name].append(
                CodeExampleMeta(
                    unq_id=pair["unq_id"],
                    lang=pair.get("lang"),
                    framework=pair.get("framework"),
                )
            )

    mechanisms = [
        MechanismMeta(mechanism_name=name, code_examples=ces)
        for name, ces in mech_map.items()
    ]

    return ConceptGraphResponse(
        concept_name=record["concept_name"],
        concept_desc=record["concept_desc"],
        cwe_id=record["cwe_id"],
        owasp_id=record["owasp_id"],
        severity=record["severity"],
        affected_components=list(record["affected_components"] or []),
        parent_domains=[n for n in record["parent_domains"] if n],
        related_concepts=[n for n in record["related_concepts"] if n],
        mechanisms=mechanisms,
    )


async def fetch_mechanism(mechanism_name: str) -> MechanismGraphResponse | None:
    driver = get_driver()
    db = get_database()

    async with driver.session(database=db) as session:
        result = await session.run(_MECHANISM_QUERY, mechanism_name=mechanism_name)
        record = await result.single()

    if record is None:
        return None

    code_examples = [
        CodeExampleMeta(
            unq_id=ce.get("unq_id") or "",
            lang=ce.get("lang"),
            framework=ce.get("framework"),
        )
        for ce in record["code_examples"]
        if ce.get("unq_id")
    ]

    return MechanismGraphResponse(
        mechanism_name=record["mechanism_name"],
        concept_name=record["concept_name"],
        code_examples=code_examples,
    )
