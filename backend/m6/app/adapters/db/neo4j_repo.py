"""Neo4j MERGE 레포지토리 — APOC 기반 멱등성 Upsert."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from neo4j import AsyncDriver

from app.domain.models import ConceptExtractionSchema

# aliases에 방어책 명사가 섞이면 다음 Resolver가 오판 — 흡수 시 필터링
_ALIAS_POISON_PATTERN = re.compile(
    r"(Protection|Defense|Mitigation|Guard|Filter|Handler)$", re.I
)


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
        """Concept + Mechanism + RootCause + Component + CodeExample MERGE (APOC 기반 멱등)."""
        async with self._driver.session(database=self._db) as session:
            tx = await session.begin_transaction()
            try:
                name = await _merge_concept_node(tx, concept)
                for mech in concept.mechanism:
                    await _merge_mechanism_node(tx, mech.mechanism_name, concept.concept_name)
                    for ce in mech.code_examples:
                        await _merge_code_example(tx, ce, mech.mechanism_name)
                if concept.root_cause:
                    await _merge_root_cause_node(tx, concept.root_cause, concept.concept_name)
                for component_name in concept.affected_components:
                    await _merge_component_node(tx, component_name, concept.concept_name)
                await tx.commit()
            except Exception:
                await tx.rollback()
                raise
        return name

    async def transplant_as_mechanism(
        self,
        incoming: ConceptExtractionSchema,
        target_name: str,
    ) -> None:
        """정책 2: 방어책 오기출 Concept을 target의 L3 Mechanism으로 격하 이식."""
        mechanism_name = _pascal_to_snake(incoming.concept_name)
        async with self._driver.session(database=self._db) as session:
            tx = await session.begin_transaction()
            try:
                await _merge_mechanism_node(tx, mechanism_name, target_name)
                for mech in incoming.mechanism:
                    await _merge_mechanism_node(tx, mech.mechanism_name, target_name)
                    for ce in mech.code_examples:
                        await _merge_code_example(tx, ce, mech.mechanism_name)
                await tx.commit()
            except Exception:
                await tx.rollback()
                raise

    async def absorb_into_target(
        self,
        incoming: ConceptExtractionSchema,
        target_name: str,
    ) -> None:
        """MERGE action: incoming 개념을 target 노드에 흡수 (새 노드 생성 없음)."""
        async with self._driver.session(database=self._db) as session:
            tx = await session.begin_transaction()
            try:
                await _absorb_concept_node(tx, incoming, target_name)
                for mech in incoming.mechanism:
                    await _merge_mechanism_node(tx, mech.mechanism_name, target_name)
                    for ce in mech.code_examples:
                        await _merge_code_example(tx, ce, mech.mechanism_name)
                if incoming.root_cause:
                    await _merge_root_cause_node(tx, incoming.root_cause, target_name)
                for comp in incoming.affected_components:
                    await _merge_component_node(tx, comp, target_name)
                # 잔존 소스 노드 정리: incoming_name과 동일한 노드가 존재하면 관계 이전 후 삭제
                await _consolidate_source_node(tx, incoming.concept_name, target_name)
                await tx.commit()
            except Exception:
                await tx.rollback()
                raise

    async def get_topology(self) -> dict[str, list[dict]]:
        """4-Layer 온톨로지 전체 토폴로지 - 노드/엣지 (force-graph 뷰어용).

        L1 Domain(가상 집계) / L2 Concept / L3 Mechanism·RootCause·Component /
        L4 CodeExample 노드와 BELONGS_TO·MITIGATED_BY·CAUSED_BY·AFFECTS·
        HAS_EXAMPLE·RELATED_TO 엣지를 반환한다.
        """
        async with self._driver.session(database=self._db) as session:
            concept_result = await session.run(
                "MATCH (c:Concept) RETURN c.name AS name, c.domains AS domains, "
                "c.cwe_id AS cwe_id, c.owasp_id AS owasp_id, c.severity AS severity, "
                "c.description_ko AS description_ko, c.aliases AS aliases, "
                "c.root_cause AS root_cause"
            )
            concept_nodes = [
                {
                    "id": record["name"],
                    "name": record["name"],
                    "node_type": "Concept",
                    "layer": "L2",
                    "status": "COMMITTED",
                    "domains": record["domains"] or [],
                    "cwe_id": record["cwe_id"],
                    "owasp_id": record["owasp_id"],
                    "severity": record["severity"],
                    "description_ko": record["description_ko"],
                    "aliases": record["aliases"] or [],
                    "root_cause": record["root_cause"],
                }
                async for record in concept_result
            ]

            mechanism_result = await session.run(
                "MATCH (c:Concept)-[:MITIGATED_BY]->(m:Mechanism) "
                "RETURN c.name AS concept_name, m.name AS name"
            )
            mechanism_nodes: dict[str, dict] = {}
            mechanism_edges: list[dict] = []
            async for record in mechanism_result:
                node_id = f"mechanism:{record['name']}"
                mechanism_nodes[node_id] = {
                    "id": node_id,
                    "name": record["name"],
                    "node_type": "Mechanism",
                    "layer": "L3",
                    "status": "COMMITTED",
                }
                mechanism_edges.append(
                    {"source": record["concept_name"], "target": node_id, "type": "MITIGATED_BY"}
                )

            root_cause_result = await session.run(
                "MATCH (c:Concept)-[:CAUSED_BY]->(r:RootCause) "
                "RETURN c.name AS concept_name, r.name AS name"
            )
            root_cause_nodes: dict[str, dict] = {}
            root_cause_edges: list[dict] = []
            async for record in root_cause_result:
                node_id = f"rootcause:{record['name']}"
                root_cause_nodes[node_id] = {
                    "id": node_id,
                    "name": record["name"],
                    "node_type": "RootCause",
                    "layer": "L3",
                    "status": "COMMITTED",
                }
                root_cause_edges.append(
                    {"source": record["concept_name"], "target": node_id, "type": "CAUSED_BY"}
                )

            component_result = await session.run(
                "MATCH (c:Concept)-[:AFFECTS]->(x:Component) "
                "RETURN c.name AS concept_name, x.name AS name"
            )
            component_nodes: dict[str, dict] = {}
            component_edges: list[dict] = []
            async for record in component_result:
                node_id = f"component:{record['name']}"
                component_nodes[node_id] = {
                    "id": node_id,
                    "name": record["name"],
                    "node_type": "Component",
                    "layer": "L3",
                    "status": "COMMITTED",
                }
                component_edges.append(
                    {"source": record["concept_name"], "target": node_id, "type": "AFFECTS"}
                )

            code_example_result = await session.run(
                "MATCH (m:Mechanism)-[:HAS_EXAMPLE]->(ce:CodeExample) "
                "RETURN m.name AS mechanism_name, ce.unq_id AS unq_id, ce.lang AS lang, "
                "ce.lang_version AS lang_version, ce.framework AS framework, "
                "ce.framework_version AS framework_version, ce.code AS code, "
                "ce.description AS description"
            )
            code_example_nodes: list[dict] = []
            code_example_edges: list[dict] = []
            async for record in code_example_result:
                node_id = f"codeexample:{record['unq_id']}"
                code_example_nodes.append(
                    {
                        "id": node_id,
                        "name": record["unq_id"],
                        "node_type": "CodeExample",
                        "layer": "L4",
                        "status": "COMMITTED",
                        "lang": record["lang"],
                        "lang_version": record["lang_version"],
                        "framework": record["framework"],
                        "framework_version": record["framework_version"],
                        "code": record["code"],
                        "description": record["description"],
                    }
                )
                code_example_edges.append(
                    {
                        "source": f"mechanism:{record['mechanism_name']}",
                        "target": node_id,
                        "type": "HAS_EXAMPLE",
                    }
                )

            related_result = await session.run(
                "MATCH (a:Concept)-[r:RELATED_TO]->(b:Concept) "
                "RETURN a.name AS source, b.name AS target, type(r) AS type"
            )
            related_edges = [
                {"source": record["source"], "target": record["target"], "type": record["type"]}
                async for record in related_result
            ]

        domain_nodes: dict[str, dict] = {}
        domain_edges: list[dict] = []
        for concept in concept_nodes:
            for domain_name in concept["domains"]:
                node_id = f"domain:{domain_name}"
                if node_id not in domain_nodes:
                    domain_nodes[node_id] = {
                        "id": node_id,
                        "name": domain_name,
                        "node_type": "Domain",
                        "layer": "L1",
                        "status": "COMMITTED",
                    }
                domain_edges.append(
                    {"source": node_id, "target": concept["id"], "type": "BELONGS_TO"}
                )

        nodes = [
            *domain_nodes.values(),
            *concept_nodes,
            *mechanism_nodes.values(),
            *root_cause_nodes.values(),
            *component_nodes.values(),
            *code_example_nodes,
        ]
        edges = [
            *domain_edges,
            *mechanism_edges,
            *root_cause_edges,
            *component_edges,
            *code_example_edges,
            *related_edges,
        ]
        return {"nodes": nodes, "edges": edges}


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
    MERGE (c)-[:MITIGATED_BY]->(m)
    """
    await tx.run(cypher, mechanism_name=mechanism_name, concept_name=concept_name)


async def _merge_root_cause_node(tx, root_cause_name: str, concept_name: str) -> None:
    cypher = """
    MERGE (r:RootCause {name: $root_cause_name})
    ON CREATE SET r.created_at = datetime()
    WITH r
    MATCH (c:Concept {name: $concept_name})
    MERGE (c)-[:CAUSED_BY]->(r)
    """
    await tx.run(cypher, root_cause_name=root_cause_name, concept_name=concept_name)


async def _merge_component_node(tx, component_name: str, concept_name: str) -> None:
    cypher = """
    MERGE (x:Component {name: $component_name})
    ON CREATE SET x.created_at = datetime()
    WITH x
    MATCH (c:Concept {name: $concept_name})
    MERGE (c)-[:AFFECTS]->(x)
    """
    await tx.run(cypher, component_name=component_name, concept_name=concept_name)


def _pascal_to_snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


async def _merge_code_example(tx, ce, mechanism_name: str) -> None:
    normalized_code = re.sub(r"\s+", " ", ce.code or "").strip()
    code_hash = hashlib.md5(normalized_code.encode()).hexdigest()[:8]
    unq_id = f"{mechanism_name}_{code_hash}"
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


async def _absorb_concept_node(
    tx, incoming: ConceptExtractionSchema, target_name: str
) -> None:
    """기존 target 노드에 incoming의 별칭·메타데이터를 흡수 (MATCH, 새 노드 생성 안 함)."""
    incoming_aliases = [
        a for a in ([incoming.concept_name] + incoming.aliases)
        if not _ALIAS_POISON_PATTERN.search(a)
    ]
    cypher = """
    MATCH (c:Concept {name: $target_name})
    SET
        c.cwe_id         = COALESCE($cwe_id, c.cwe_id),
        c.owasp_id       = COALESCE($owasp_id, c.owasp_id),
        c.severity       = COALESCE($severity, c.severity),
        c.description_ko = COALESCE(
                             CASE WHEN $description_ko <> '' THEN $description_ko END,
                             c.description_ko),
        c.root_cause     = COALESCE(
                             CASE WHEN $root_cause <> '' THEN $root_cause END,
                             c.root_cause),
        c.aliases        = apoc.coll.toSet(c.aliases + $incoming_aliases),
        c.domains        = apoc.coll.toSet(c.domains + $domains),
        c.updated_at     = datetime()
    """
    await tx.run(
        cypher,
        target_name=target_name,
        cwe_id=incoming.cwe_id,
        owasp_id=incoming.owasp_id,
        severity=incoming.severity,
        description_ko=incoming.description_ko or "",
        root_cause=incoming.root_cause or "",
        incoming_aliases=incoming_aliases,
        domains=incoming.domains,
    )


async def _consolidate_source_node(tx, incoming_name: str, target_name: str) -> None:
    """MERGE 완료 후 incoming_name 노드가 Neo4j에 잔존하면 관계를 target으로 이전하고 삭제.

    이전 파이프라인 버그나 시드 데이터로 생성된 고립 노드(예: CsrfAttack)가
    CSRF와 별개로 남아 그래프가 파편화되는 현상을 방지한다.
    """
    if incoming_name == target_name:
        return
    for rel_type in ("MITIGATED_BY", "CAUSED_BY", "AFFECTS"):
        await tx.run(
            f"MATCH (src:Concept {{name: $src}})-[:{rel_type}]->(node) "
            f"MATCH (tgt:Concept {{name: $tgt}}) "
            f"MERGE (tgt)-[:{rel_type}]->(node)",
            src=incoming_name, tgt=target_name,
        )
    await tx.run(
        "MATCH (src:Concept {name: $src})-[:RELATED_TO]->(rel:Concept) "
        "WHERE rel.name <> $tgt "
        "MATCH (tgt:Concept {name: $tgt}) "
        "MERGE (tgt)-[:RELATED_TO]->(rel)",
        src=incoming_name, tgt=target_name,
    )
    await tx.run(
        "MATCH (src:Concept {name: $src}) DETACH DELETE src",
        src=incoming_name,
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
