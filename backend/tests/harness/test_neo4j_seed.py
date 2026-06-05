"""P1-T7 통합 테스트 — Neo4j APOC 다중 라벨 시드 (PRD-schema.md §15.3).

T07: 보안 도메인 온톨로지 노드 — Domain/OWASPCategory/CWE MERGE 멱등성
T08: 보안 Concept APOC 다중 라벨 — :Concept:Security 물리 라벨 검증
T09: 성능 Concept APOC 다중 라벨 — :Concept:Performance 물리 라벨 검증
T10: 교차 도메인 Concept — :Concept:Security:Performance 물리 라벨 검증
T11: MERGE 멱등성 — 동일 Concept MERGE 2회 시 노드 1개만 존재
"""

import uuid
import pytest


# ── 헬퍼 Cypher ────────────────────────────────────────────────────────────

_MERGE_DOMAIN = """
MERGE (d:Domain {name: $name})
ON CREATE SET d.description_ko = $description_ko
RETURN d.name AS name
"""

_MERGE_OWASP = """
MERGE (o:OWASPCategory {owasp_id: $owasp_id})
ON CREATE SET o.name        = $name,
              o.severity    = $severity,
              o.description_ko = $description_ko
RETURN o.owasp_id AS owasp_id
"""

_MERGE_CWE = """
MERGE (c:CWE {cwe_id: $cwe_id})
ON CREATE SET c.name         = $name,
              c.description_ko = $description_ko
RETURN c.cwe_id AS cwe_id
"""

_MERGE_CONCEPT = """
MERGE (c:Concept {name: $name})
ON CREATE SET c.cwe_id         = $cwe_id,
              c.severity        = $severity,
              c.description_ko  = $description_ko,
              c.aliases         = $aliases,
              c.concept_domain  = $concept_domain,
              c.created_at      = timestamp()
ON MATCH  SET c.updated_at     = timestamp()
RETURN c.name AS name
"""

_ADD_LABELS = """
MATCH (c:Concept {name: $name})
CALL apoc.create.addLabels(c, $labels) YIELD node
RETURN node.name AS name
"""

_CLEANUP_CONCEPT = "MATCH (c:Concept {name: $name}) DETACH DELETE c"


# ── 도우미 함수 ────────────────────────────────────────────────────────────

def _merge_concept_with_labels(session, name, cwe_id, severity, description_ko,
                                aliases, concept_domain):
    """Concept MERGE 후 concept_domain에 따라 APOC addLabels 적용."""
    domain_label_map = {
        "security":     ["Security"],
        "performance":  ["Performance"],
        "both":         ["Security", "Performance"],
    }
    labels = domain_label_map[concept_domain]

    session.run(
        _MERGE_CONCEPT,
        name=name, cwe_id=cwe_id, severity=severity,
        description_ko=description_ko, aliases=aliases,
        concept_domain=concept_domain,
    )
    session.run(_ADD_LABELS, name=name, labels=labels)


# ── T07: 보안 도메인 온톨로지 노드 ────────────────────────────────────────


def test_T07_domain_node_merge_idempotent(neo4j_driver):
    """Arrange: Domain(Security) MERGE.
    Act: 동일 Cypher 2회 실행.
    Assert: Domain 노드 1개.
    """
    with neo4j_driver.session() as session:
        session.run(_MERGE_DOMAIN, name="Security", description_ko="보안 도메인 테스트")
        session.run(_MERGE_DOMAIN, name="Security", description_ko="보안 도메인 테스트")

        count = session.run(
            "MATCH (d:Domain {name:'Security'}) RETURN count(d) AS n"
        ).single()["n"]
        assert count == 1, f"Domain 노드 {count}개 — MERGE 멱등성 실패"


def test_T07_owasp_category_merge(neo4j_driver):
    """Arrange: OWASPCategory A03:2025 MERGE.
    Act: 동일 Cypher 2회.
    Assert: OWASPCategory 노드 1개.
    """
    owasp_id = "A03:2025-test"
    with neo4j_driver.session() as session:
        try:
            for _ in range(2):
                session.run(
                    _MERGE_OWASP,
                    owasp_id=owasp_id, name="Injection-test",
                    severity="CRITICAL", description_ko="인젝션 테스트",
                )
            count = session.run(
                "MATCH (o:OWASPCategory {owasp_id:$id}) RETURN count(o) AS n",
                id=owasp_id,
            ).single()["n"]
            assert count == 1
        finally:
            session.run("MATCH (o:OWASPCategory {owasp_id:$id}) DETACH DELETE o", id=owasp_id)


def test_T07_cwe_node_merge(neo4j_driver):
    """Arrange: CWE-79 MERGE.
    Act: 2회.
    Assert: CWE 노드 1개.
    """
    cwe_id = "CWE-9999-test"
    with neo4j_driver.session() as session:
        try:
            for _ in range(2):
                session.run(_MERGE_CWE, cwe_id=cwe_id, name="XSS-test", description_ko="테스트")
            count = session.run(
                "MATCH (c:CWE {cwe_id:$id}) RETURN count(c) AS n", id=cwe_id
            ).single()["n"]
            assert count == 1
        finally:
            session.run("MATCH (c:CWE {cwe_id:$id}) DETACH DELETE c", id=cwe_id)


# ── T08: 보안 Concept APOC 다중 라벨 ──────────────────────────────────────


def test_T08_security_concept_apoc_label(neo4j_driver):
    """Arrange: concept_domain='security' 인 Concept.
    Act: MERGE + apoc.create.addLabels(["Security"]).
    Assert: MATCH (c:Concept:Security {name:...}) 1건.
    """
    name = f"XSS_apoc_{uuid.uuid4().hex[:6]}"
    with neo4j_driver.session() as session:
        try:
            _merge_concept_with_labels(
                session, name, "CWE-79", "HIGH",
                "APOC 라벨 테스트 보안 컨셉",
                ["Cross-Site Scripting"], "security",
            )

            count = session.run(
                "MATCH (c:Concept:Security {name:$name}) RETURN count(c) AS n", name=name
            ).single()["n"]
            assert count == 1, ":Concept:Security 물리 라벨 부여 실패"

            # :Concept:Performance 라벨은 없어야 함
            perf_count = session.run(
                "MATCH (c:Concept:Performance {name:$name}) RETURN count(c) AS n", name=name
            ).single()["n"]
            assert perf_count == 0, "security 전용 Concept에 :Performance 라벨이 붙으면 안 됨"
        finally:
            session.run(_CLEANUP_CONCEPT, name=name)


# ── T09: 성능 Concept APOC 다중 라벨 ──────────────────────────────────────


def test_T09_performance_concept_apoc_label(neo4j_driver):
    """Arrange: concept_domain='performance' 인 Concept.
    Act: MERGE + apoc.create.addLabels(["Performance"]).
    Assert: MATCH (c:Concept:Performance {name:...}) 1건.
    """
    name = f"N1Query_apoc_{uuid.uuid4().hex[:6]}"
    with neo4j_driver.session() as session:
        try:
            _merge_concept_with_labels(
                session, name, "CWE-1072", "HIGH",
                "APOC 라벨 테스트 성능 컨셉",
                ["N+1 Problem"], "performance",
            )

            count = session.run(
                "MATCH (c:Concept:Performance {name:$name}) RETURN count(c) AS n", name=name
            ).single()["n"]
            assert count == 1, ":Concept:Performance 물리 라벨 부여 실패"

            sec_count = session.run(
                "MATCH (c:Concept:Security {name:$name}) RETURN count(c) AS n", name=name
            ).single()["n"]
            assert sec_count == 0, "performance 전용 Concept에 :Security 라벨이 붙으면 안 됨"
        finally:
            session.run(_CLEANUP_CONCEPT, name=name)


# ── T10: 교차 도메인 Concept :Concept:Security:Performance ─────────────────


def test_T10_both_domain_concept_dual_labels(neo4j_driver):
    """Arrange: concept_domain='both' 인 Concept (MemoryLeak).
    Act: MERGE + apoc.create.addLabels(["Security","Performance"]).
    Assert: MATCH (c:Concept:Security:Performance {name:...}) 1건.
    """
    name = f"MemoryLeak_apoc_{uuid.uuid4().hex[:6]}"
    with neo4j_driver.session() as session:
        try:
            _merge_concept_with_labels(
                session, name, "CWE-401", "HIGH",
                "교차 도메인 APOC 라벨 테스트",
                ["Memory Leak", "메모리 누수"], "both",
            )

            # 두 라벨 동시 보유 확인
            count = session.run(
                "MATCH (c:Concept:Security:Performance {name:$name}) RETURN count(c) AS n",
                name=name,
            ).single()["n"]
            assert count == 1, ":Concept:Security:Performance 물리 다중 라벨 부여 실패"

            # 보안 단독 조회도 가능해야 함
            sec = session.run(
                "MATCH (c:Concept:Security {name:$name}) RETURN count(c) AS n", name=name
            ).single()["n"]
            assert sec == 1, "both Concept이 :Concept:Security 조회에도 노출돼야 함"

            # 성능 단독 조회도 가능해야 함
            perf = session.run(
                "MATCH (c:Concept:Performance {name:$name}) RETURN count(c) AS n", name=name
            ).single()["n"]
            assert perf == 1, "both Concept이 :Concept:Performance 조회에도 노출돼야 함"
        finally:
            session.run(_CLEANUP_CONCEPT, name=name)


# ── T11: MERGE 멱등성 (APOC 포함) ─────────────────────────────────────────


def test_T11_concept_merge_idempotent_with_apoc(neo4j_driver):
    """Arrange: 동일 Concept name.
    Act: MERGE + addLabels를 3회 반복.
    Assert: Concept 노드 1개, :Security 라벨 1번만 부여(중복 없음).
    """
    name = f"CSRF_idem_{uuid.uuid4().hex[:6]}"
    with neo4j_driver.session() as session:
        try:
            for _ in range(3):
                _merge_concept_with_labels(
                    session, name, "CWE-352", "HIGH",
                    "CSRF 멱등성 테스트",
                    ["CSRF", "Cross-Site Request Forgery"], "security",
                )

            count = session.run(
                "MATCH (c:Concept {name:$name}) RETURN count(c) AS n", name=name
            ).single()["n"]
            assert count == 1, f"MERGE 3회 후 노드 {count}개 — 중복 생성됨"

            # 라벨 확인 — 물리 라벨은 한 번만 붙어야 함
            labels_result = session.run(
                "MATCH (c:Concept {name:$name}) RETURN labels(c) AS labels", name=name
            ).single()["labels"]
            label_set = set(labels_result)
            assert "Concept" in label_set
            assert "Security" in label_set
            # 중복 라벨은 Neo4j가 허용하지 않으므로 labels() 반환 시 중복 없음 (APOC 보장)
        finally:
            session.run(_CLEANUP_CONCEPT, name=name)
