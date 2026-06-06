"""Neo4j 온톨로지 시드 스크립트 v3.

APOC addLabels로 물리적 다중 라벨(:Concept:security:performance) 부여.
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
SEC_DIR  = SEED_DIR / "security"
PERF_DIR = SEED_DIR / "performance"

# ── 인덱스 ────────────────────────────────────────────────────────────────

_INDEXES = [
    "CREATE INDEX domain_name_idx        IF NOT EXISTS FOR (d:Domain)                  ON (d.name)",
    "CREATE INDEX owasp_id_idx           IF NOT EXISTS FOR (o:OWASPCategory)           ON (o.owasp_id)",
    "CREATE INDEX perf_cat_name_idx      IF NOT EXISTS FOR (p:PerfAntipatternCategory) ON (p.name)",
    "CREATE INDEX cwe_id_idx             IF NOT EXISTS FOR (c:CWE)                     ON (c.cwe_id)",
    "CREATE INDEX concept_name_idx       IF NOT EXISTS FOR (c:Concept)                 ON (c.name)",
    "CREATE INDEX secmech_name_idx       IF NOT EXISTS FOR (s:SecurityMechanism)       ON (s.name)",
    "CREATE INDEX rootcause_name_idx     IF NOT EXISTS FOR (r:RootCause)               ON (r.name)",
    "CREATE INDEX component_name_idx     IF NOT EXISTS FOR (comp:Component)            ON (comp.name)",
    "CREATE INDEX document_doc_id_idx    IF NOT EXISTS FOR (doc:Document)              ON (doc.doc_id)",
]

# ── Cypher 템플릿 ─────────────────────────────────────────────────────────

_MERGE_DOMAIN = """
MERGE (d:Domain {name: $name})
ON CREATE SET d.description_ko = $description_ko
"""

_MERGE_OWASP = """
MERGE (o:OWASPCategory {owasp_id: $owasp_id})
ON CREATE SET o.name           = $name,
              o.severity       = $severity,
              o.description_ko = $description_ko
"""

_MERGE_PERF_CAT = """
MERGE (p:PerfAntipatternCategory {name: $name})
ON CREATE SET p.authority      = $authority,
              p.description_ko = $description_ko
"""

_MERGE_CWE = """
MERGE (c:CWE {cwe_id: $cwe_id})
ON CREATE SET c.name           = $name,
              c.description_ko = $description_ko
"""

_BELONGS_TO_DOMAIN_OWASP = """
MATCH (d:Domain {name: 'security'}), (o:OWASPCategory {owasp_id: $owasp_id})
MERGE (d)-[:BELONGS_TO]->(o)
"""

_BELONGS_TO_DOMAIN_PERF = """
MATCH (d:Domain {name: 'performance'}), (p:PerfAntipatternCategory {name: $name})
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
              c.owasp_id       = $owasp_id,
              c.severity       = $severity,
              c.domains        = $domains,
              c.concept_type   = $concept_type,
              c.description_ko = $description_ko,
              c.aliases        = $aliases,
              c.created_at     = timestamp()
ON MATCH  SET c.updated_at     = timestamp()
"""

# list()로 결과 강제 소비 — 드라이버가 쿼리 완료를 보장하도록 함
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


# ── 적재 함수 ─────────────────────────────────────────────────────────────

def _seed_indexes(session):
    for cypher in _INDEXES:
        session.run(cypher)


def _seed_security_domain(session, data: dict):
    """Domain(security) → OWASPCategory → CWE."""
    domain = data["domain"]
    session.run(_MERGE_DOMAIN, name=domain["name"].lower(), description_ko=domain["description_ko"])

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

    for cat in data["owasp_categories"]:
        for cwe_id in cat.get("cwe_ids", []):
            session.run(_MAPS_TO_CWE, owasp_id=cat["owasp_id"], cwe_id=cwe_id)


def _seed_performance_domain(session, data: dict):
    """Domain(performance) → PerfAntipatternCategory → CWE."""
    domain = data["domain"]
    session.run(_MERGE_DOMAIN, name=domain["name"].lower(), description_ko=domain["description_ko"])

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
    """Concept MERGE + APOC 다중 라벨 + 온톨로지 관계 전체."""
    for c in concepts:
        name    = c["name"]
        domains = c.get("domains", [])  # 입력 배열 직접 사용, 하드코딩 맵 없음

        # 1. Concept 노드 MERGE
        session.run(
            _MERGE_CONCEPT,
            name=name,
            cwe_id=c.get("cwe_id", ""),
            owasp_id=c.get("owasp_id", ""),
            severity=c.get("severity", "").lower(),
            domains=[d.lower() for d in domains],
            concept_type=c.get("concept_type", "").lower(),
            description_ko=c.get("description_ko", ""),
            aliases=c.get("aliases", []),
        )

        # 2. APOC 다중 라벨 — list()로 강제 소비하여 완료 보장
        #    domains 배열을 PascalCase로 변환하여 직접 주입 (하드코딩 맵 없음)
        labels = [d.capitalize() for d in domains]
        if labels:
            rows = list(session.run(_ADD_LABELS, name=name, labels=labels))
            if not rows:
                print(
                    f"  WARNING: APOC addLabels 결과 없음 '{name}' — APOC 플러그인 확인 필요",
                    file=sys.stderr,
                )

        # 3. CWE → Concept INSTANTIATED_BY
        if c.get("cwe_id"):
            session.run(_INSTANTIATED_BY, cwe_id=c["cwe_id"], name=name)

        # 4. PerfAntipatternCategory -[:REF_TO]-> CWE
        #    perf_category 필드가 있는 모든 개념에 생성 — 이 관계가 없으면 성능 온톨로지와 고립됨
        perf_cat = c.get("perf_category", "")
        if perf_cat and c.get("cwe_id"):
            session.run(_REF_TO_CWE, cat_name=perf_cat, cwe_id=c["cwe_id"])

        # 5. SecurityMechanism + MITIGATED_BY
        for mech in c.get("security_mechanism", []):
            session.run(_MERGE_SEC_MECH, name=mech)
            session.run(_MITIGATED_BY, cname=name, mname=mech)

        # 6. RootCause + CAUSED_BY
        if c.get("root_cause"):
            root_name = c["root_cause"][:120]
            session.run(_MERGE_ROOT_CAUSE, name=root_name, description_ko=root_name)
            session.run(_CAUSED_BY, cname=name, rname=root_name)

        # 7. Component + AFFECTS
        for comp in c.get("affected_components", []):
            session.run(_MERGE_COMPONENT, name=comp)
            session.run(_AFFECTS, cname=name, compname=comp)


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

            print("▶ 보안 Concept 시드 적재...")
            _seed_concepts(session, sec_concepts)

            print("▶ 성능/교차 Concept 시드 적재...")
            _seed_concepts(session, perf_concepts)

            def _count(label):
                return session.run(f"MATCH (n:{label}) RETURN count(n) AS n").single()["n"]

            domain_names = [r["name"] for r in session.run("MATCH (d:Domain) RETURN d.name AS name")]
            owasp_count  = _count("OWASPCategory")
            perf_count   = _count("PerfAntipatternCategory")
            cwe_count    = _count("CWE")
            concept_count = _count("Concept")
            sec_count    = _count("Concept:security")
            perf_c_count = _count("Concept:performance")
            both_count   = _count("Concept:security:performance")

            print(f"""
==================================================================
 지식 그래프 시드 적재 완료
==================================================================
   Domain 목록        : {domain_names}
   OWASPCategory      : {owasp_count}
   PerfCategory       : {perf_count}
   CWE                : {cwe_count}
   Concept (총합)     : {concept_count}
   ├─ :security       : {sec_count}
   ├─ :performance    : {perf_c_count}
   └─ :security:performance  : {both_count}  ← 교차 도메인
==================================================================
""")
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
