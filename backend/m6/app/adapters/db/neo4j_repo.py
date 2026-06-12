"""Neo4j MERGE 레포지토리 — APOC 기반 멱등성 Upsert."""

from __future__ import annotations

import re
from pathlib import Path

from neo4j import AsyncDriver

from app.domain.models import ConceptExtractionSchema


class Neo4jConceptRepo:
    def __init__(self, driver: AsyncDriver, database: str = "neo4j") -> None:
        self._driver = driver
        self._db = database

    async def init_schema(self, cypher_path: Path) -> None:
        """init_db.cypher 실행 — 제약조건 + 인덱스 (멱등)."""
        raw = cypher_path.read_text(encoding="utf-8")
        statements = [
            s.strip()
            for s in re.split(r";", raw)
            if s.strip()
        ]
        async with self._driver.session(database=self._db) as session:
            for stmt in statements:
                lines = [ln for ln in stmt.splitlines() if not ln.strip().startswith("//")]
                body = "\n".join(lines).strip()
                if body:
                    await session.run(body)

    async def merge_concept(self, concept: ConceptExtractionSchema) -> str:
        """Concept + Mechanism + CodeExample MERGE (APOC 기반 멱등)."""
        async with self._driver.session(database=self._db) as session:
            tx = await session.begin_transaction()
            try:
                name = await _merge_concept_node(tx, concept)
                for mech in concept.mechanism:
                    await _merge_mechanism_node(tx, mech.mechanism_name, concept.concept_name)
                    for ce in mech.code_examples:
                        await _merge_code_example(tx, ce, mech.mechanism_name)
                await tx.commit()
            except Exception:
                await tx.rollback()
                raise
        return name


async def _merge_concept_node(tx, concept: ConceptExtractionSchema) -> str:
    domain_labels = [d.capitalize() for d in concept.domains if d]
    cypher = """
    MERGE (c:Concept {name: $name})
    ON CREATE SET
        c.concept_type   = $concept_type,
        c.cwe_id         = $cwe_id,
        c.owasp_id       = $owasp_id,
        c.severity       = $severity,
        c.description_ko = $description_ko,
        c.root_cause     = $root_cause,
        c.aliases        = $aliases,
        c.domains        = $domains,
        c.created_at     = datetime()
    ON MATCH SET
        c.cwe_id         = COALESCE($cwe_id, c.cwe_id),
        c.owasp_id       = COALESCE($owasp_id, c.owasp_id),
        c.severity       = COALESCE($severity, c.severity),
        c.description_ko = COALESCE($description_ko, c.description_ko),
        c.root_cause     = COALESCE($root_cause, c.root_cause),
        c.aliases        = apoc.coll.toSet(c.aliases + $aliases),
        c.domains        = apoc.coll.toSet(c.domains + $domains),
        c.updated_at     = datetime()
    WITH c
    CALL apoc.create.addLabels(c, $labels) YIELD node
    RETURN node.name AS name
    """
    result = await tx.run(
        cypher,
        name=concept.concept_name,
        concept_type=concept.concept_type,
        cwe_id=concept.cwe_id,
        owasp_id=concept.owasp_id,
        severity=concept.severity,
        description_ko=concept.description_ko,
        root_cause=concept.root_cause,
        aliases=concept.aliases,
        domains=concept.domains,
        labels=domain_labels,
    )
    record = await result.single()
    return record["name"]


async def _merge_mechanism_node(tx, mechanism_name: str, concept_name: str) -> None:
    cypher = """
    MERGE (m:Mechanism {name: $mechanism_name})
    ON CREATE SET m.created_at = datetime()
    WITH m
    MATCH (c:Concept {name: $concept_name})
    MERGE (c)-[:HAS_MECHANISM]->(m)
    """
    await tx.run(cypher, mechanism_name=mechanism_name, concept_name=concept_name)


async def _merge_code_example(tx, ce, mechanism_name: str) -> None:
    unq_id = (
        f"{mechanism_name}_{ce.lang}_{ce.lang_version}"
        f"_{ce.framework}_{ce.framework_version}"
    )
    cypher = """
    MERGE (ce:CodeExample {unq_id: $unq_id})
    ON CREATE SET
        ce.lang              = $lang,
        ce.lang_version      = $lang_version,
        ce.framework         = $framework,
        ce.framework_version = $framework_version,
        ce.code              = $code,
        ce.description       = $description,
        ce.created_at        = datetime()
    ON MATCH SET
        ce.code        = $code,
        ce.description = $description,
        ce.updated_at  = datetime()
    WITH ce
    MATCH (m:Mechanism {name: $mechanism_name})
    MERGE (m)-[:HAS_EXAMPLE]->(ce)
    """
    await tx.run(
        cypher,
        unq_id=unq_id,
        lang=ce.lang,
        lang_version=ce.lang_version,
        framework=ce.framework,
        framework_version=ce.framework_version,
        code=ce.code,
        description=ce.description,
        mechanism_name=mechanism_name,
    )


async def merge_related_to(
    driver: AsyncDriver, source_name: str, target_name: str, database: str = "neo4j"
) -> None:
    """RELATED_TO 엣지 생성 — 양 노드 존재 확인 후 생성 (순서 보장)."""
    cypher = """
    MATCH (source:Concept {name: $source_name})
    MATCH (target:Concept {name: $target_name})
    MERGE (source)-[:RELATED_TO]->(target)
    """
    async with driver.session(database=database) as session:
        await session.run(cypher, source_name=source_name, target_name=target_name)
