"""Neo4j 온톨로지 시드 스크립트 v2.

APOC addLabels를 사용하여 물리적 다중 라벨(:Concept:Security:Performance)을 부여.
Neo4j Community Edition + APOC 플러그인 필수.

Usage:
    python backend/scripts/seed_neo4j.py
"""

import json
import os
import sys
from pathlib import Path

from neo4j import GraphDatabase

SEED_DIR = Path(__file__).parent / "seed"
SEC_DIR = SEED_DIR / "security"
PERF_DIR = SEED_DIR / "performance"

# ── 노드 인덱스 ───────────────────────────────────────────────────────────

_INDEXES = [
    "CREATE INDEX domain_name_idx IF NOT EXISTS FOR (d:Domain) ON (d.name)",
    "CREATE INDEX owasp_id_idx IF NOT EXISTS FOR (o:OWASPCategory) ON (o.owasp_id)",
    "CREATE INDEX perf_cat_name_idx IF NOT EXISTS FOR (p:PerfAntipatternCategory) ON (p.name)",
    "CREATE INDEX cwe_id_idx IF NOT EXISTS FOR (c:CWE) ON (c.cwe_id)",
    "CREATE INDEX concept_name_idx IF NOT EXISTS FOR (c:Concept) ON (c.name)",
    "CREATE INDEX secmech_name_idx IF NOT EXISTS FOR (s:SecurityMechanism) ON (s.name)",
    "CREATE INDEX rootcause_name_idx IF NOT EXISTS FOR (r:RootCause) ON (r.name)",
    "CREATE INDEX component_name_idx IF NOT EXISTS FOR (comp:Component) ON (comp.name)",
    "CREATE INDEX document_doc_id_idx IF NOT EXISTS FOR (doc:Document) ON (doc.doc_id)",
]

# ── Cypher 템플릿 ─────────────────────────────────────────────────────────

_MERGE_DOMAIN = """
MERGE (d:Domain {name: $name})
ON CREATE SET d.description_ko = $description_ko
"""

_MERGE_OWASP = """
MERGE (o:OWASPCategory {owasp_id: $owasp_id})
ON CREATE SET o.name         = $name,
              o.severity     = $severity,
              o.description_ko = $description_ko
"""

_MERGE_PERF_CAT = """
MERGE (p:PerfAntipatternCategory {name: $name})
ON CREATE SET p.authority    = $authority,
              p.description_ko = $description_ko
"""

_MERGE_CWE = """
MERGE (c:CWE {cwe_id: $cwe_id})
ON CREATE SET c.name         = $name,
              c.description_ko = $description_ko
"""

_BELONGS_TO_DOMAIN_OWASP = """
MATCH (d:Domain {name:'Security'}), (o:OWASPCategory {owasp_id: $owasp_id})
MERGE (d)-[:BELONGS_TO]->(o)
"""

_BELONGS_TO_DOMAIN_PERF = """
MATCH (d:Domain {name:'Performance'}), (p:PerfAntipatternCategory {name: $name})
MERGE (d)-[:BELONGS_TO]->(p)
"""

_MAPS_TO_CWE = """
MATCH (o:OWASPCategory {owasp_id: $owasp_id}), (c:CWE {cwe_id: $cwe_id})
MERGE (o)-[:MAPS_TO]->(c)
"""

_REF_TO_CWE = """
MATCH (p:PerfAntipatternCategory {name: $cat_name}), (c:CWE {cwe_id: $cwe_id})
MERGE (p)-[:REF_TO]->(c)
"""

_MERGE_CONCEPT = """
MERGE (c:Concept {name: $name})
ON CREATE SET c.cwe_id         = $cwe_id,
              c.owasp_id        = $owasp_id,
              c.severity        = $severity,
              c.concept_domain  = $concept_domain,
              c.concept_type    = $concept_type,
              c.description_ko  = $description_ko,
              c.aliases         = $aliases,
              c.created_at      = timestamp()
ON MATCH  SET c.updated_at     = timestamp()
"""

_ADD_LABELS = """
MATCH (c:Concept {name: $name})
CALL apoc.create.addLabels(c, $labels) YIELD node
RETURN node.name AS name
"""

_INSTANTIATED_BY = """
MATCH (cwe:CWE {cwe_id: $cwe_id}), (con:Concept {name: $name})
MERGE (cwe)-[:INSTANTIATED_BY]->(con)
"""

_MERGE_SEC_MECH = """
MERGE (m:SecurityMechanism {name: $name})
ON CREATE SET m.description_ko = ''
"""

_MITIGATED_BY = """
MATCH (c:Concept {name: $cname}), (m:SecurityMechanism {name: $mname})
MERGE (c)-[:MITIGATED_BY]->(m)
"""

_MERGE_ROOT_CAUSE = """
MERGE (r:RootCause {name: $name})
ON CREATE SET r.description_ko = $description_ko
"""

_CAUSED_BY = """
MATCH (c:Concept {name: $cname}), (r:RootCause {name: $rname})
MERGE (c)-[:CAUSED_BY]->(r)
"""

_MERGE_COMPONENT = """
MERGE (comp:Component {name: $name})
ON CREATE SET comp.description_ko = ''
"""

_AFFECTS = """
MATCH (c:Concept {name: $cname}), (comp:Component {name: $compname})
MERGE (c)-[:AFFECTS]->(comp)
"""

# ── 도메인 라벨 매핑 ─────────────────────────────────────────────────────

DOMAIN_LABEL_MAP = {
    "security":    ["Security"],
    "performance": ["Performance"],
    "both":        ["Security", "Performance"],
}


# ── 적재 함수 ─────────────────────────────────────────────────────────────

def _seed_indexes(session):
    for cypher in _INDEXES:
        session.run(cypher)


def _seed_security_domain(session, data: dict):
    """Domain(Security) → OWASPCategory → CWE."""
    domain = data["domain"]
    session.run(_MERGE_DOMAIN, name=domain["name"], description_ko=domain["description_ko"])

    for cat in data["owasp_categories"]:
        session.run(
            _MERGE_OWASP,
            owasp_id=cat["owasp_id"],
            name=cat["name"],
            severity=cat["severity"],
            description_ko=cat["description_ko"],
        )
        session.run(_BELONGS_TO_DOMAIN_OWASP, owasp_id=cat["owasp_id"])

    for cwe in data["cwe_nodes"]:
        session.run(
            _MERGE_CWE,
            cwe_id=cwe["cwe_id"],
            name=cwe["name"],
            description_ko=cwe["description_ko"],
        )

    # OWASP → CWE MAPS_TO 관계
    for cat in data["owasp_categories"]:
        for cwe_id in cat.get("cwe_ids", []):
            session.run(_MAPS_TO_CWE, owasp_id=cat["owasp_id"], cwe_id=cwe_id)


def _seed_performance_domain(session, data: dict):
    """Domain(Performance) → PerfAntipatternCategory → CWE."""
    domain = data["domain"]
    session.run(_MERGE_DOMAIN, name=domain["name"], description_ko=domain["description_ko"])

    for cat in data["perf_antipattern_categories"]:
        session.run(
            _MERGE_PERF_CAT,
            name=cat["name"],
            authority=cat["authority"],
            description_ko=cat["description_ko"],
        )
        session.run(_BELONGS_TO_DOMAIN_PERF, name=cat["name"])

    for cwe in data["cwe_nodes"]:
        session.run(
            _MERGE_CWE,
            cwe_id=cwe["cwe_id"],
            name=cwe["name"],
            description_ko=cwe["description_ko"],
        )


def _seed_concepts(session, concepts: list):
    """Concept 노드 MERGE + APOC addLabels + 관계."""
    for c in concepts:
        name = c["name"]
        domain = c["concept_domain"]

        session.run(
            _MERGE_CONCEPT,
            name=name,
            cwe_id=c.get("cwe_id", ""),
            owasp_id=c.get("owasp_id", ""),
            severity=c.get("severity", ""),
            concept_domain=domain,
            concept_type=c.get("concept_type", ""),
            description_ko=c.get("description_ko", ""),
            aliases=c.get("aliases", []),
        )

        # APOC 다중 라벨 부여
        labels = DOMAIN_LABEL_MAP.get(domain, [])
        if labels:
            session.run(_ADD_LABELS, name=name, labels=labels)

        # CWE → Concept INSTANTIATED_BY
        if c.get("cwe_id"):
            session.run(_INSTANTIATED_BY, cwe_id=c["cwe_id"], name=name)

        # SecurityMechanism + MITIGATED_BY
        for mech in c.get("security_mechanisms", []):
            session.run(_MERGE_SEC_MECH, name=mech)
            session.run(_MITIGATED_BY, cname=name, mname=mech)

        # RootCause + CAUSED_BY
        if c.get("root_cause"):
            root_name = c["root_cause"][:120]  # 길이 제한
            session.run(_MERGE_ROOT_CAUSE, name=root_name, description_ko=root_name)
            session.run(_CAUSED_BY, cname=name, rname=root_name)

        # Component + AFFECTS
        for comp in c.get("affected_components", []):
            session.run(_MERGE_COMPONENT, name=comp)
            session.run(_AFFECTS, cname=name, compname=comp)


def _perf_concept_to_category_ref(session, concepts: list, perf_data: dict):
    """성능 Concept → PerfAntipatternCategory REF_TO (CWE 경유)."""
    cat_cwe_map = {cat["name"]: [] for cat in perf_data["perf_antipattern_categories"]}
    for cwe in perf_data["cwe_nodes"]:
        # perf_data CWE와 concept의 cwe_id 매칭으로 카테고리 REF_TO 생성
        pass

    for c in concepts:
        cat = c.get("perf_category", "")
        cwe_id = c.get("cwe_id", "")
        if cat and cwe_id:
            session.run(_REF_TO_CWE, cat_name=cat, cwe_id=cwe_id)


# ── 진입점 ────────────────────────────────────────────────────────────────

def main():
    uri  = os.getenv("NEO4J_URI",      "bolt://127.0.0.1:7687")
    user = os.getenv("NEO4J_USER",     "neo4j")
    pw   = os.getenv("NEO4J_PASSWORD", "pass1234!")

    sec_domain_data  = json.loads((SEC_DIR  / "domain_security.json").read_text("utf-8"))
    perf_domain_data = json.loads((PERF_DIR / "domain_performance.json").read_text("utf-8"))
    sec_concepts     = json.loads((SEC_DIR  / "security_concepts.json").read_text("utf-8"))["concepts"]
    perf_concepts    = json.loads((PERF_DIR / "perf_concepts.json").read_text("utf-8"))["concepts"]

    driver = GraphDatabase.driver(uri, auth=(user, pw))
    try:
        with driver.session() as session:
            print("▶ 인덱스 생성...")
            _seed_indexes(session)

            print("▶ 보안 도메인 온톨로지 적재...")
            _seed_security_domain(session, sec_domain_data)

            print("▶ 성능 도메인 온톨로지 적재...")
            _seed_performance_domain(session, perf_domain_data)

            print("▶ 보안 Concept 시드 적재 (APOC addLabels)...")
            _seed_concepts(session, sec_concepts)

            print("▶ 성능/교차 Concept 시드 적재 (APOC addLabels)...")
            _seed_concepts(session, perf_concepts)

            # 통계 출력 — Neo4j 5.18 호환 구문 사용
            def _count(label):
                return session.run(f"MATCH (n:{label}) RETURN count(n) AS n").single()["n"]

            domains = [r["name"] for r in session.run("MATCH (d:Domain) RETURN d.name AS name")]
            owasp_count   = _count("OWASPCategory")
            perf_count    = _count("PerfAntipatternCategory")
            cwe_count     = _count("CWE")
            concept_count = _count("Concept")
            sec_count     = _count("Concept:Security")
            perf_c_count  = _count("Concept:Performance")
            both_count    = _count("Concept:Security:Performance")

            print(f"""
seed OK:
   Domain       : {domains}
   OWASPCategory: {owasp_count}
   PerfCategory : {perf_count}
   CWE          : {cwe_count}
   Concept total: {concept_count}
   :Security    : {sec_count}
   :Performance : {perf_c_count}
   :Both        : {both_count}
""")
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
