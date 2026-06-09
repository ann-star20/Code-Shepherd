"""Neo4j 4-레이어 지식 그래프 저장소.

완전 멱등성 보장:
  Concept     → MERGE ON name  (fulltext alias 선처리 중복 방지)
  Mechanism   → MERGE ON name  (소문자 스네이크케이스 정규화 키)
  Property    → MERGE ON unq_key
  CodeExample → MERGE ON unq_id  (mech_lang_lang_ver_fw_fw_ver 복합키)
  Document    → MERGE ON id    (해싱 키)

APOC 의존:
  apoc.create.addLabels  — 동적 도메인 라벨 누적 (Security, Performance)
  apoc.coll.toSet        — aliases / domains 중복 제거 병합
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from neo4j import AsyncDriver, AsyncManagedTransaction

from app.domain.models import ConceptExtractionSchema, ConceptUpdate

log = logging.getLogger(__name__)

_LABEL_MAP = {"security": "Security", "performance": "Performance"}


def _to_snake(s: str) -> str:
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", s)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s).lower()
    s = re.sub(r"[\s\-\.]+", "_", s)
    s = re.sub(r"[^a-z0-9_]", "", s)
    return s.strip("_")


class Neo4jConceptRepo:
    """
    4-레이어 지식 그래프 완전 멱등성 저장소.

    모든 쓰기 연산은 execute_write 관리 트랜잭션 내에서 원자적으로 실행된다.
    같은 데이터를 반복 투입해도 중복 노드·관계를 절대 생성하지 않는다.
    """

    def __init__(self, driver: AsyncDriver) -> None:
        self._driver = driver

    # ─── 스키마 초기화 ────────────────────────────────────────────────────────

    async def init_schema(self, cypher_path: Path) -> None:
        """init_db.cypher를 실행하여 8대 제약조건 + 인덱스를 생성한다."""
        raw = cypher_path.read_text(encoding="utf-8")
        statements: list[str] = []
        current: list[str] = []

        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("//") or stripped.startswith("--"):
                continue
            if ";" in stripped:
                parts = stripped.split(";", 1)
                current.append(parts[0].strip())
                stmt = " ".join(current).strip()
                if stmt:
                    statements.append(stmt)
                current = [parts[1].strip()] if parts[1].strip() else []
            else:
                current.append(stripped)

        if current:
            stmt = " ".join(current).strip()
            if stmt:
                statements.append(stmt)

        async with self._driver.session() as session:
            for stmt in statements:
                try:
                    await session.run(stmt)
                except Exception as exc:
                    log.warning("Schema stmt skipped (%.50s…): %s", stmt, exc)

        log.info("[schema] %d statements applied from %s", len(statements), cypher_path.name)

    # ─── Alias 기반 중복 방지 선처리 ─────────────────────────────────────────

    async def find_master_by_alias(self, alias: str) -> str | None:
        """
        풀텍스트 인덱스에서 alias를 검색하여 기존 마스터 Concept.name 반환.
        미등록이면 None.
        """
        safe = alias.replace("\\", "\\\\").replace('"', '\\"')
        async with self._driver.session() as session:
            result = await session.run(
                "CALL db.index.fulltext.queryNodes"
                '("concept_aliases_fulltext_idx", $q) '
                "YIELD node, score "
                "RETURN node.name AS master_name "
                "ORDER BY score DESC LIMIT 1",
                q=safe,
            )
            record = await result.single()
            return record["master_name"] if record else None

    # ─── 핵심 MERGE 오케스트레이션 ───────────────────────────────────────────

    async def merge_concept(self, concept: ConceptExtractionSchema) -> str:
        """
        ConceptExtractionSchema 전체를 4-레이어 그래프로 멱등성 MERGE.

        반환값: 마스터 노드의 name (alias 충돌 시 기존 name으로 수렴).
        """
        master_name = concept.concept_name
        existing = await self.find_master_by_alias(concept.concept_name)
        if existing and existing != concept.concept_name:
            log.info("[dedup] '%s' → master '%s'", concept.concept_name, existing)
            master_name = existing

        async with self._driver.session() as session:
            await session.execute_write(_write_concept_tx, concept, master_name)

        log.info(
            "[merge] concept='%s' domains=%s mechs=%d props=%d",
            master_name,
            concept.domains,
            len(concept.mechanisms),
            len(concept.properties),
        )
        return master_name

    # ─── 단건 조회 ────────────────────────────────────────────────────────────

    async def get_concept(self, name: str) -> dict[str, Any] | None:
        async with self._driver.session() as session:
            result = await session.run(
                "MATCH (c:Concept {name: $name}) RETURN properties(c) AS props",
                name=name,
            )
            record = await result.single()
            return dict(record["props"]) if record else None

    # ─── 부분 수정 ────────────────────────────────────────────────────────────

    async def update_concept(self, name: str, update: ConceptUpdate) -> None:
        """
        Concept 노드 속성 부분 수정.
        domains가 포함된 경우 BELONGS_TO 관계 재배선 및 APOC 라벨 추가.
        """
        props = update.to_neo4j_dict()
        domains = props.pop("domains", None)

        async with self._driver.session() as session:
            if props:
                await session.run(
                    """
                    MATCH (c:Concept {name: $name})
                    SET c += $props
                    SET c.updated_at = timestamp()
                    """,
                    name=name,
                    props=props,
                )

            if domains is not None:
                # 기존 도메인 관계 전부 제거 후 재배선 (인간 어드민 수정 정책)
                await session.run(
                    "MATCH (c:Concept {name: $name})-[r:BELONGS_TO]->(:Domain) DELETE r",
                    name=name,
                )
                for domain in domains:
                    await session.run(
                        """
                        MERGE (d:Domain {name: $domain})
                        ON CREATE SET d.created_at = timestamp()
                        WITH d
                        MATCH (c:Concept {name: $name})
                        MERGE (c)-[:BELONGS_TO]->(d)
                        """,
                        domain=domain,
                        name=name,
                    )
                new_labels = [_LABEL_MAP[d] for d in domains if d in _LABEL_MAP]
                if new_labels:
                    await session.run(
                        """
                        MATCH (c:Concept {name: $name})
                        CALL apoc.create.addLabels(c, $labels) YIELD node
                        RETURN node
                        """,
                        name=name,
                        labels=new_labels,
                    )

    # ─── MERGE 수렴 후 Mechanism 보강 ────────────────────────────────────────

    async def merge_mechanisms(
        self,
        concept: ConceptExtractionSchema,
        master_name: str,
    ) -> None:
        """MERGE 분기: 기존 master 노드에 신규 Mechanism/CodeExample만 추가.

        Concept 노드 재생성·속성 덮어쓰기 없이 Layer 3/4만 병합한다.
        """
        async with self._driver.session() as session:
            await session.execute_write(_write_mechanisms_only_tx, concept, master_name)

    # ─── 연쇄 삭제 ────────────────────────────────────────────────────────────

    async def delete_concept(self, name: str) -> None:
        """
        Concept DETACH DELETE.
        해당 Concept에만 연결된 고아 Mechanism·CodeExample도 함께 삭제.
        """
        async with self._driver.session() as session:
            await session.execute_write(_delete_concept_tx, name)
        log.info("[delete] concept='%s'", name)

    # ─── Document MERGE ───────────────────────────────────────────────────────

    async def merge_document(
        self,
        doc_id: str,
        title: str = "",
        source: str = "",
        raw_url: str = "",
    ) -> None:
        """Document 노드 멱등성 MERGE."""
        async with self._driver.session() as session:
            await session.run(
                """
                MERGE (doc:Document {id: $id})
                ON CREATE SET
                    doc.title      = $title,
                    doc.source     = $source,
                    doc.raw_url    = $raw_url,
                    doc.created_at = timestamp()
                """,
                id=doc_id,
                title=title,
                source=source,
                raw_url=raw_url,
            )

    async def link_document_to_concept(self, doc_id: str, concept_name: str) -> None:
        """Document → Concept REFERENCES 엣지 생성."""
        async with self._driver.session() as session:
            await session.run(
                """
                MATCH (doc:Document {id: $doc_id})
                MATCH (c:Concept {name: $name})
                MERGE (doc)-[:REFERENCES]->(c)
                """,
                doc_id=doc_id,
                name=concept_name,
            )

    # ─── 토폴로지 조회 ────────────────────────────────────────────────────────

    async def get_topology(
        self,
        domains: list[str] | None = None,
        search: str | None = None,
        limit: int = 200,
    ) -> dict[str, list[dict]]:
        """3-레이어 토폴로지(Domain→Concept→Mechanism)를 nodes/edges 형태로 반환.

        CodeExample/Property/RootCause/Component는 하단 패널 전용으로 포함하지 않는다.
        """
        conditions = []
        if domains:
            conditions.append("any(d IN c.domains WHERE d IN $domains)")
        if search:
            conditions.append(
                "(toLower(c.name) CONTAINS toLower($search)"
                " OR any(a IN c.aliases WHERE toLower(a) CONTAINS toLower($search)))"
            )
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        async with self._driver.session() as session:
            result = await session.run(
                f"""
                MATCH (c:Concept) {where}
                OPTIONAL MATCH (c)-[:BELONGS_TO]->(d:Domain)
                OPTIONAL MATCH (c)-[:MITIGATED_BY]->(m:Mechanism)
                RETURN c, d, m
                LIMIT $limit
                """,
                domains=domains or [],
                search=search or "",
                limit=limit,
            )
            records = await result.data()

        nodes: dict[str, dict] = {}
        edges: list[dict] = []

        def _add_node(n: Any, label: str) -> str | None:
            if n is None:
                return None
            nid = n.get("name") or n.get("id", "")
            if nid and nid not in nodes:
                nodes[nid] = {"id": nid, "label": label, **dict(n)}
            return nid or None

        for row in records:
            cid = _add_node(row.get("c"), "Concept")
            did = _add_node(row.get("d"), "Domain")
            mid = _add_node(row.get("m"), "Mechanism")

            for src, tgt, rel in [
                (cid, did, "BELONGS_TO"),
                (cid, mid, "MITIGATED_BY"),
            ]:
                if src and tgt:
                    edges.append({"source": src, "target": tgt, "type": rel})

        return {"nodes": list(nodes.values()), "edges": edges}

    # ─── 코드 예제 조회 ──────────────────────────────────────────────────────────

    async def get_concept_code(
        self,
        name: str,
        lang: str | None = None,
        framework: str | None = None,
    ) -> dict:
        """Concept → Mechanism → CodeExample 경로를 조회해 반환.

        lang / framework 필터가 있으면 해당 조건으로 좁힌다.
        없으면 모든 CodeExample을 반환해 프론트에서 필터링할 수 있도록 한다.
        """
        conditions = ["toLower(c.name) = toLower($name)"]
        if lang:
            conditions.append("toLower(ce.lang) = toLower($lang)")
        if framework:
            conditions.append("toLower(ce.framework) = toLower($framework)")
        where = "WHERE " + " AND ".join(conditions)

        async with self._driver.session() as session:
            result = await session.run(
                f"""
                MATCH (c:Concept)-[:MITIGATED_BY]->(m:Mechanism)-[:HAS_EXAMPLE]->(ce:CodeExample)
                {where}
                RETURN m.name AS mechanism, ce
                ORDER BY m.name, ce.lang, ce.framework
                LIMIT 50
                """,
                name=name,
                lang=lang or "",
                framework=framework or "",
            )
            records = await result.data()

        items = []
        langs: set[str] = set()
        frameworks: set[str] = set()
        for row in records:
            ce = dict(row.get("ce") or {})
            if not ce:
                continue
            ce["mechanism"] = row.get("mechanism", "")
            items.append(ce)
            if ce.get("lang"):
                langs.add(ce["lang"])
            if ce.get("framework"):
                frameworks.add(ce["framework"])

        return {
            "concept": name,
            "langs": sorted(langs),
            "frameworks": sorted(frameworks),
            "examples": items,
        }


# ─── 트랜잭션 함수 ────────────────────────────────────────────────────────────

async def _write_concept_tx(
    tx: AsyncManagedTransaction,
    concept: ConceptExtractionSchema,
    master_name: str,
) -> None:
    """단일 트랜잭션 내에서 4-레이어 전체 노드·관계를 MERGE."""

    # ── Layer 2: Concept 노드 ─────────────────────────────────────────────────
    effective_severity = "low" if concept.severity == "info" else concept.severity
    # concept_name도 aliases에 포함 → 풀텍스트 검색 범위 확보
    all_aliases = list(dict.fromkeys([concept.concept_name] + concept.aliases))

    await tx.run(
        """
        MERGE (c:Concept {name: $name})
        ON CREATE SET
            c.concept_type   = $concept_type,
            c.cwe_id         = $cwe_id,
            c.owasp_id       = $owasp_id,
            c.severity       = $severity,
            c.domains        = $domains,
            c.description_ko = $description_ko,
            c.aliases        = $aliases,
            c.is_deprecated  = false,
            c.created_at     = timestamp()
        ON MATCH SET
            c.updated_at     = timestamp(),
            c.aliases        = apoc.coll.toSet(c.aliases + $aliases),
            c.domains        = apoc.coll.toSet(c.domains + $domains)
        """,
        name=master_name,
        concept_type=concept.concept_type,
        cwe_id=concept.cwe_id,
        owasp_id=concept.owasp_id,
        severity=effective_severity,
        domains=concept.domains,
        description_ko=concept.description_ko,
        aliases=all_aliases,
    )

    # APOC 동적 도메인 라벨 누적 (Security / Performance / both)
    if concept.neo4j_extra_labels:
        await tx.run(
            """
            MATCH (c:Concept {name: $name})
            CALL apoc.create.addLabels(c, $labels) YIELD node
            RETURN node
            """,
            name=master_name,
            labels=concept.neo4j_extra_labels,
        )

    # ── Layer 1: Domain → BELONGS_TO ──────────────────────────────────────────
    for domain in concept.domains:
        await tx.run(
            """
            MERGE (d:Domain {name: $domain})
            ON CREATE SET d.created_at = timestamp()
            WITH d
            MATCH (c:Concept {name: $name})
            MERGE (c)-[:BELONGS_TO]->(d)
            """,
            domain=domain,
            name=master_name,
        )

    # ── Layer 3: Mechanism → MITIGATED_BY / Layer 4: CodeExample → HAS_EXAMPLE
    # MATCH (c) 선행 후 MERGE (m) / MERGE (c)-[]->(m) 패턴 사용:
    # WITH...MATCH 역순 패턴은 MATCH가 0행 반환 시 관계 생성이 누락됨.
    for mech in concept.mechanisms:
        await tx.run(
            """
            MATCH (c:Concept {name: $concept_name})
            MERGE (m:Mechanism {name: $mech_name})
            ON CREATE SET m.created_at = timestamp()
            MERGE (c)-[:MITIGATED_BY]->(m)
            """,
            mech_name=mech.mechanism_name,
            concept_name=master_name,
        )

        for ex in mech.code_examples:
            if not ex.code:
                continue
            unq_id = (
                f"{mech.mechanism_name}_{ex.lang}_{ex.lang_version}"
                f"_{ex.framework}_{ex.framework_version}"
            )
            await tx.run(
                """
                MATCH (m:Mechanism {name: $mech_name})
                MERGE (ce:CodeExample {unq_id: $unq_id})
                ON CREATE SET
                    ce.lang              = $lang,
                    ce.lang_version      = $lang_version,
                    ce.framework         = $framework,
                    ce.framework_version = $fw_ver,
                    ce.code              = $code,
                    ce.description       = $description,
                    ce.created_at        = timestamp()
                MERGE (m)-[:HAS_EXAMPLE]->(ce)
                """,
                unq_id=unq_id,
                lang=ex.lang,
                lang_version=ex.lang_version,
                framework=ex.framework,
                fw_ver=ex.framework_version,
                code=ex.code,
                description=ex.description,
                mech_name=mech.mechanism_name,
            )

    # ── Layer 3: Property → TUNED_BY ─────────────────────────────────────────
    for prop in concept.properties:
        if not prop.key:
            continue
        await tx.run(
            """
            MATCH (c:Concept {name: $concept_name})
            MERGE (p:Property {unq_key: $unq_key})
            ON CREATE SET
                p.value      = $value,
                p.type       = $type,
                p.created_at = timestamp()
            ON MATCH SET
                p.value = $value
            MERGE (c)-[:TUNED_BY]->(p)
            """,
            unq_key=prop.key,
            value=prop.value,
            type=prop.type,
            concept_name=master_name,
        )

    # ── Layer 3: RootCause → CAUSED_BY ───────────────────────────────────────
    if concept.root_cause:
        rc_name = _to_snake(concept.root_cause)
        await tx.run(
            """
            MATCH (c:Concept {name: $concept_name})
            MERGE (r:RootCause {name: $rc_name})
            ON CREATE SET r.created_at = timestamp()
            MERGE (c)-[:CAUSED_BY]->(r)
            """,
            rc_name=rc_name,
            concept_name=master_name,
        )

    # ── Layer 3: Component → AFFECTS ─────────────────────────────────────────
    for comp in concept.affected_components:
        comp_name = _to_snake(comp)
        await tx.run(
            """
            MATCH (c:Concept {name: $concept_name})
            MERGE (x:Component {name: $comp_name})
            ON CREATE SET x.created_at = timestamp()
            MERGE (c)-[:AFFECTS]->(x)
            """,
            comp_name=comp_name,
            concept_name=master_name,
        )

    # ── Document → REFERENCES ─────────────────────────────────────────────────
    if concept.doc_id:
        await tx.run(
            """
            MATCH (doc:Document {id: $doc_id})
            MATCH (c:Concept {name: $name})
            MERGE (doc)-[:REFERENCES]->(c)
            """,
            doc_id=concept.doc_id,
            name=master_name,
        )


async def _write_mechanisms_only_tx(
    tx: AsyncManagedTransaction,
    concept: ConceptExtractionSchema,
    master_name: str,
) -> None:
    """Concept 노드 생성 없이 Mechanism/CodeExample 만 master 노드에 MERGE.

    MERGE 수렴 분기에서 target 노드에 신규 코드 예제를 병합할 때 호출된다.
    unq_id 기준 ON CREATE SET: 동일 버전 조합이 이미 있으면 건너뜀.
    """
    for mech in concept.mechanisms:
        await tx.run(
            """
            MATCH (c:Concept {name: $concept_name})
            MERGE (m:Mechanism {name: $mech_name})
            ON CREATE SET m.created_at = timestamp()
            MERGE (c)-[:MITIGATED_BY]->(m)
            """,
            mech_name=mech.mechanism_name,
            concept_name=master_name,
        )

        for ex in mech.code_examples:
            if not ex.code:
                continue
            unq_id = (
                f"{mech.mechanism_name}_{ex.lang}_{ex.lang_version}"
                f"_{ex.framework}_{ex.framework_version}"
            )
            await tx.run(
                """
                MATCH (m:Mechanism {name: $mech_name})
                MERGE (ce:CodeExample {unq_id: $unq_id})
                ON CREATE SET
                    ce.lang              = $lang,
                    ce.lang_version      = $lang_version,
                    ce.framework         = $framework,
                    ce.framework_version = $fw_ver,
                    ce.code              = $code,
                    ce.description       = $description,
                    ce.created_at        = timestamp()
                MERGE (m)-[:HAS_EXAMPLE]->(ce)
                """,
                unq_id=unq_id,
                lang=ex.lang,
                lang_version=ex.lang_version,
                framework=ex.framework,
                fw_ver=ex.framework_version,
                code=ex.code,
                description=ex.description,
                mech_name=mech.mechanism_name,
            )


async def _delete_concept_tx(tx: AsyncManagedTransaction, name: str) -> None:
    """고아 Mechanism·CodeExample 연쇄 삭제 후 Concept DETACH DELETE."""
    result = await tx.run(
        """
        MATCH (c:Concept {name: $name})-[:MITIGATED_BY]->(m:Mechanism)
        WHERE NOT EXISTS {
            MATCH (other:Concept)-[:MITIGATED_BY]->(m)
            WHERE other.name <> $name
        }
        RETURN m.name AS mech_name
        """,
        name=name,
    )
    records = await result.data()
    orphan_mechs = [r["mech_name"] for r in records]

    if orphan_mechs:
        await tx.run(
            """
            MATCH (m:Mechanism) WHERE m.name IN $names
            OPTIONAL MATCH (m)-[:HAS_EXAMPLE]->(ce:CodeExample)
            DETACH DELETE ce, m
            """,
            names=orphan_mechs,
        )

    await tx.run(
        "MATCH (c:Concept {name: $name}) DETACH DELETE c",
        name=name,
    )
