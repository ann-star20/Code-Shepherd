"""통합 테스트 — Neo4jConceptRepo (4-레이어 신 아키텍처).

Neo4j 미실행 시 자동 skip (conftest.py async_neo4j_driver 픽스처).

커버:
  I01 merge_concept 멱등성         — 2회 투입 시 Concept 노드 1개
  I02 Mechanism MITIGATED_BY 엣지  — 관계 생성 및 중복 방지
  I03 CodeExample HAS_EXAMPLE 엣지 — unq_id 복합키 중복 방지
  I04 Property TUNED_BY 엣지       — unq_key 중복 방지
  I05 :Security 물리 라벨           — APOC addLabels 보안 도메인
  I06 :Performance 물리 라벨        — APOC addLabels 성능 도메인
  I07 :Security:Performance 교차    — APOC 두 라벨 동시 부여
  I08 delete_concept 연쇄 삭제      — 고아 Mechanism·CodeExample 제거
  I09 update_concept 부분 수정      — SET 이후 속성 갱신
  I10 구형 list[str] mechanism 수렴 — 레거시 포맷 정상 처리
"""

import uuid
from pathlib import Path

import pytest

from app.adapters.db.neo4j_repo import Neo4jConceptRepo
from app.domain.models import ConceptExtractionSchema, ConceptUpdate

_CYPHER_PATH = Path(__file__).parents[2] / "scripts" / "init_db.cypher"


# ── 픽스처 ────────────────────────────────────────────────────────────────────


@pytest.fixture
async def repo(async_neo4j_driver):
    r = Neo4jConceptRepo(async_neo4j_driver)
    await r.init_schema(_CYPHER_PATH)
    return r


def _uid() -> str:
    return uuid.uuid4().hex[:6]


def _concept(name: str, **kwargs) -> ConceptExtractionSchema:
    defaults = {
        "concept_name": name,
        "concept_type": "vulnerability_root_cause",
        "cwe_id": "CWE-79",
        "owasp_id": "A03:2025",
        "severity": "high",
        "domains": ["security"],
        "description_ko": "테스트용 개념",
        "aliases": [f"alias_{name}"],
    }
    defaults.update(kwargs)
    return ConceptExtractionSchema(**defaults)


# ── I01: merge_concept 멱등성 ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_I01_merge_concept_idempotent(repo, async_neo4j_driver):
    name = f"XSS_I01_{_uid()}"
    try:
        c = _concept(name)
        await repo.merge_concept(c)
        await repo.merge_concept(c)  # 2회

        async with async_neo4j_driver.session() as session:
            r = await session.run(
                "MATCH (c:Concept {name: $name}) RETURN count(c) AS n", name=name
            )
            assert (await r.single())["n"] == 1, "MERGE 2회 후 중복 노드 생성"
    finally:
        async with async_neo4j_driver.session() as session:
            await session.run(
                "MATCH (c:Concept {name: $name}) DETACH DELETE c", name=name
            )


# ── I02: Mechanism MITIGATED_BY 엣지 ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_I02_mechanism_edge_created(repo, async_neo4j_driver):
    name = f"SQLi_I02_{_uid()}"
    mech = "parameterized_query"
    try:
        c = _concept(
            name,
            security_mechanism=[{"mechanism_name": mech, "code_examples": []}],
        )
        await repo.merge_concept(c)

        async with async_neo4j_driver.session() as session:
            r = await session.run(
                """
                MATCH (c:Concept {name:$name})-[:MITIGATED_BY]->(m:Mechanism {name:$mech})
                RETURN count(m) AS n
                """,
                name=name,
                mech=mech,
            )
            assert (await r.single())["n"] == 1, "MITIGATED_BY 엣지 없음"
    finally:
        async with async_neo4j_driver.session() as session:
            await session.run(
                "MATCH (c:Concept {name:$name}) DETACH DELETE c", name=name
            )


# ── I03: CodeExample HAS_EXAMPLE 엣지 + unq_id 중복 방지 ──────────────────────


@pytest.mark.asyncio
async def test_I03_code_example_edge_and_unq_id(repo, async_neo4j_driver):
    name = f"CSRF_I03_{_uid()}"
    mech_n = f"csrf_token_{_uid()}"
    try:
        c = _concept(
            name,
            security_mechanism=[
                {
                    "mechanism_name": mech_n,
                    "code_examples": [
                        {
                            "lang": "python",
                            "lang_version": ">=3.10",
                            "framework": "django",
                            "framework_version": ">=4.0",
                            "code": "# test csrf",
                        }
                    ],
                }
            ],
        )
        await repo.merge_concept(c)
        await repo.merge_concept(c)  # 2회 — CodeExample 중복 없어야 함

        async with async_neo4j_driver.session() as session:
            r = await session.run(
                """
                MATCH (:Mechanism {name:$m})-[:HAS_EXAMPLE]->(ce:CodeExample)
                RETURN count(ce) AS n
                """,
                m=mech_n,
            )
            assert (await r.single())["n"] == 1, "HAS_EXAMPLE 중복 생성"
    finally:
        async with async_neo4j_driver.session() as session:
            await session.run(
                "MATCH (c:Concept {name:$name}) DETACH DELETE c", name=name
            )
            await session.run("MATCH (m:Mechanism {name:$m}) DETACH DELETE m", m=mech_n)


# ── I04: Property TUNED_BY 엣지 ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_I04_property_edge_created(repo, async_neo4j_driver):
    name = f"Prop_I04_{_uid()}"
    unq_key = f"test_prop_{_uid()}"
    try:
        c = _concept(
            name,
            config_properties=[{"key": unq_key, "value": "True", "type": "security"}],
        )
        await repo.merge_concept(c)

        async with async_neo4j_driver.session() as session:
            r = await session.run(
                """
                MATCH (c:Concept {name:$name})-[:TUNED_BY]->(p:Property {unq_key:$key})
                RETURN count(p) AS n
                """,
                name=name,
                key=unq_key,
            )
            assert (await r.single())["n"] == 1, "TUNED_BY 엣지 없음"
    finally:
        async with async_neo4j_driver.session() as session:
            await session.run(
                "MATCH (c:Concept {name:$name}) DETACH DELETE c", name=name
            )
            await session.run(
                "MATCH (p:Property {unq_key:$key}) DETACH DELETE p", key=unq_key
            )


# ── I05: :Security 물리 라벨 ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_I05_security_label_applied(repo, async_neo4j_driver):
    name = f"SecLabel_I05_{_uid()}"
    try:
        await repo.merge_concept(_concept(name, domains=["security"]))

        async with async_neo4j_driver.session() as session:
            r = await session.run(
                "MATCH (c:Concept:Security {name:$name}) RETURN count(c) AS n",
                name=name,
            )
            assert (await r.single())["n"] == 1, ":Security 라벨 없음"

            r2 = await session.run(
                "MATCH (c:Concept:Performance {name:$name}) RETURN count(c) AS n",
                name=name,
            )
            assert (await r2.single())["n"] == 0, "security 전용에 :Performance 불필요"
    finally:
        async with async_neo4j_driver.session() as session:
            await session.run(
                "MATCH (c:Concept {name:$name}) DETACH DELETE c", name=name
            )


# ── I06: :Performance 물리 라벨 ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_I06_performance_label_applied(repo, async_neo4j_driver):
    name = f"PerfLabel_I06_{_uid()}"
    try:
        await repo.merge_concept(
            _concept(name, domains=["performance"], owasp_id=None, cwe_id="CWE-1048")
        )

        async with async_neo4j_driver.session() as session:
            r = await session.run(
                "MATCH (c:Concept:Performance {name:$name}) RETURN count(c) AS n",
                name=name,
            )
            assert (await r.single())["n"] == 1, ":Performance 라벨 없음"
    finally:
        async with async_neo4j_driver.session() as session:
            await session.run(
                "MATCH (c:Concept {name:$name}) DETACH DELETE c", name=name
            )


# ── I07: :Security:Performance 교차 도메인 ────────────────────────────────────


@pytest.mark.asyncio
async def test_I07_cross_domain_both_labels(repo, async_neo4j_driver):
    name = f"MemLeak_I07_{_uid()}"
    try:
        await repo.merge_concept(
            _concept(name, domains=["performance", "security"], cwe_id="CWE-401")
        )

        async with async_neo4j_driver.session() as session:
            r = await session.run(
                "MATCH (c:Concept:Security:Performance {name:$name}) RETURN count(c) AS n",
                name=name,
            )
            assert (await r.single())["n"] == 1, ":Security:Performance 교차 라벨 없음"
    finally:
        async with async_neo4j_driver.session() as session:
            await session.run(
                "MATCH (c:Concept {name:$name}) DETACH DELETE c", name=name
            )


# ── I08: delete_concept 연쇄 삭제 ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_I08_delete_concept_cascade(repo, async_neo4j_driver):
    name = f"DelTest_I08_{_uid()}"
    mech_name = f"only_mech_{_uid()}"
    try:
        c = _concept(
            name,
            security_mechanism=[{"mechanism_name": mech_name, "code_examples": []}],
        )
        await repo.merge_concept(c)

        # 삭제 전 Mechanism 존재 확인
        async with async_neo4j_driver.session() as session:
            r = await session.run(
                "MATCH (m:Mechanism {name:$m}) RETURN count(m) AS n", m=mech_name
            )
            assert (await r.single())["n"] == 1

        await repo.delete_concept(name)

        async with async_neo4j_driver.session() as session:
            r_c = await session.run(
                "MATCH (c:Concept {name:$name}) RETURN count(c) AS n", name=name
            )
            assert (await r_c.single())["n"] == 0, "Concept 삭제 실패"

            r_m = await session.run(
                "MATCH (m:Mechanism {name:$m}) RETURN count(m) AS n", m=mech_name
            )
            assert (await r_m.single())["n"] == 0, "고아 Mechanism 삭제 실패"
    finally:
        async with async_neo4j_driver.session() as session:
            await session.run(
                "MATCH (c:Concept {name:$name}) DETACH DELETE c", name=name
            )
            await session.run(
                "MATCH (m:Mechanism {name:$m}) DETACH DELETE m", m=mech_name
            )


# ── I09: update_concept 부분 수정 ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_I09_update_concept_partial(repo, async_neo4j_driver):
    name = f"UpdTest_I09_{_uid()}"
    try:
        await repo.merge_concept(_concept(name, severity="low", description_ko="원본"))
        await repo.update_concept(
            name, ConceptUpdate(severity="critical", description_ko="수정됨")
        )

        node = await repo.get_concept(name)
        assert node is not None
        assert node["severity"] == "critical"
        assert node["description_ko"] == "수정됨"
    finally:
        async with async_neo4j_driver.session() as session:
            await session.run(
                "MATCH (c:Concept {name:$name}) DETACH DELETE c", name=name
            )


# ── I10: 구형 list[str] mechanism 수렴 ────────────────────────────────────────


@pytest.mark.asyncio
async def test_I10_legacy_str_mechanism_merged(repo, async_neo4j_driver):
    name = f"Legacy_I10_{_uid()}"
    try:
        c = ConceptExtractionSchema(
            concept_name=name,
            domains=["security"],
            security_mechanism=["OutputEncoding", "ContentSecurityPolicy"],
        )
        master = await repo.merge_concept(c)

        async with async_neo4j_driver.session() as session:
            r = await session.run(
                """
                MATCH (c:Concept {name:$name})-[:MITIGATED_BY]->(m:Mechanism)
                RETURN count(m) AS n
                """,
                name=master,
            )
            assert (await r.single())[
                "n"
            ] == 2, "구형 str mechanism 2개 MITIGATED_BY 연결 실패"
    finally:
        async with async_neo4j_driver.session() as session:
            await session.run(
                "MATCH (c:Concept {name:$name}) DETACH DELETE c", name=name
            )
