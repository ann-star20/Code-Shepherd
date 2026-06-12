"""G9: commit_staging usecase 통합 테스트.

커버:
  C01 APPROVED 2행 → concepts 테이블 2행 INSERT
  C02 APPROVED 2행 → staging_concepts 모두 COMMITTED
  C03 APPROVED 1행 → Neo4j Concept 노드 1개 (Neo4jConceptRepo.merge_concept)
  C04 APPROVED 0행 → 반환값 0, 예외 없음
"""

import json
import uuid
from pathlib import Path

import pytest
from app.adapters.db.neo4j_repo import Neo4jConceptRepo
from app.usecases.commit_staging import commit_staging

_CYPHER_PATH = Path(__file__).parents[2] / "scripts" / "init_db.cypher"


# ── 픽스처 ────────────────────────────────────────────────────────────────────


@pytest.fixture
async def neo4j_repo(async_neo4j_driver):
    """스키마 초기화 완료된 Neo4jConceptRepo."""
    repo = Neo4jConceptRepo(async_neo4j_driver)
    await repo.init_schema(_CYPHER_PATH)
    return repo


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────


def _uid(base: str) -> str:
    return f"{base}_{uuid.uuid4().hex[:6]}"


async def _insert_doc(conn, doc_id: str) -> None:
    await conn.execute(
        "INSERT INTO knowledge_documents (doc_id, source_prefix, original_url, content_hash) "
        "VALUES ($1,'EXT','https://example.com/commit-test','abcd1234') ON CONFLICT DO NOTHING",
        doc_id,
    )


async def _insert_approved(conn, session_id: str, doc_id: str, name: str) -> None:
    cj = json.dumps(
        {
            "concept_name": name,
            "domains": ["security"],
            "severity": "high",
            "description_ko": "테스트",
            "aliases": [],
            "security_mechanism": [],
            "affected_components": [],
            "config_properties": [],
        }
    )
    await conn.execute(
        """INSERT INTO staging_concepts
           (session_id, doc_id, concept_json, state, known_domains, unknown_domains)
           VALUES ($1::uuid, $2, $3::jsonb, 'APPROVED', $4, '{}')""",
        session_id,
        doc_id,
        cj,
        ["security"],
    )


async def _cleanup_pg(
    conn, session_id: str, doc_id: str, concept_names: list[str]
) -> None:
    await conn.execute(
        "DELETE FROM staging_concepts WHERE session_id = $1::uuid", session_id
    )
    if concept_names:
        await conn.execute(
            "DELETE FROM concepts WHERE concept_name = ANY($1)", concept_names
        )
    await conn.execute("DELETE FROM knowledge_documents WHERE doc_id = $1", doc_id)


async def _cleanup_neo4j(driver, names: list[str]) -> None:
    async with driver.session() as s:
        await s.run(
            "UNWIND $names AS n MATCH (c:Concept {name: n}) DETACH DELETE c",
            names=names,
        )


# ── C01: concepts 테이블 INSERT ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_C01_commit_writes_concepts(asyncpg_pool, async_neo4j_driver, neo4j_repo):
    """
    Arrange: staging 2행 APPROVED
    Act:     commit_staging(repo) 호출
    Assert:  concepts 테이블에 2행 삽입
    """
    session_id = str(uuid.uuid4())
    doc_id = f"EXT_cs_{uuid.uuid4().hex[:8]}"
    names = [_uid("XSS"), _uid("SQLI")]

    async with asyncpg_pool.acquire() as conn:
        await _insert_doc(conn, doc_id)
        for n in names:
            await _insert_approved(conn, session_id, doc_id, n)
        try:
            count = await commit_staging(session_id, conn, neo4j_repo)
            assert count == 2

            rows = await conn.fetch(
                "SELECT concept_name FROM concepts WHERE concept_name = ANY($1)", names
            )
            assert len(rows) == 2
        finally:
            await _cleanup_pg(conn, session_id, doc_id, names)
    await _cleanup_neo4j(async_neo4j_driver, names)


# ── C02: staging_concepts → COMMITTED ────────────────────────────────────────


@pytest.mark.asyncio
async def test_C02_commit_state_committed(asyncpg_pool, async_neo4j_driver, neo4j_repo):
    """
    Arrange: staging 2행 APPROVED
    Act:     commit_staging(repo) 호출
    Assert:  staging_concepts 전행 state='COMMITTED'
    """
    session_id = str(uuid.uuid4())
    doc_id = f"EXT_cs_{uuid.uuid4().hex[:8]}"
    names = [_uid("XSS"), _uid("SQLI")]

    async with asyncpg_pool.acquire() as conn:
        await _insert_doc(conn, doc_id)
        for n in names:
            await _insert_approved(conn, session_id, doc_id, n)
        try:
            await commit_staging(session_id, conn, neo4j_repo)

            states = await conn.fetch(
                "SELECT state FROM staging_concepts WHERE session_id = $1::uuid",
                session_id,
            )
            assert all(r["state"] == "COMMITTED" for r in states)
        finally:
            await _cleanup_pg(conn, session_id, doc_id, names)
    await _cleanup_neo4j(async_neo4j_driver, names)


# ── C03: Neo4j Concept 노드 생성 확인 ────────────────────────────────────────


@pytest.mark.asyncio
async def test_C03_commit_neo4j_concept_created(
    asyncpg_pool, async_neo4j_driver, neo4j_repo
):
    """
    Arrange: XSS APPROVED staging 1행
    Act:     commit_staging(repo) 호출
    Assert:  Neo4j에 Concept{name} 노드 1개
    """
    session_id = str(uuid.uuid4())
    doc_id = f"EXT_cs_{uuid.uuid4().hex[:8]}"
    name = _uid("XSS")

    async with asyncpg_pool.acquire() as conn:
        await _insert_doc(conn, doc_id)
        await _insert_approved(conn, session_id, doc_id, name)
        try:
            await commit_staging(session_id, conn, neo4j_repo)
        finally:
            await _cleanup_pg(conn, session_id, doc_id, [name])

    try:
        async with async_neo4j_driver.session() as s:
            result = await s.run(
                "MATCH (c:Concept {name: $name}) RETURN count(c) AS n", name=name
            )
            record = await result.single()
        assert record["n"] == 1
    finally:
        await _cleanup_neo4j(async_neo4j_driver, [name])


# ── C04: 0행 APPROVED → 반환 0 ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_C04_commit_zero_returns_zero(
    asyncpg_pool, async_neo4j_driver, neo4j_repo
):
    """
    Arrange: staging 0행 APPROVED
    Act:     commit_staging(repo) 호출
    Assert:  반환값 0, 예외 없음
    """
    session_id = str(uuid.uuid4())
    doc_id = f"EXT_cs_{uuid.uuid4().hex[:8]}"

    async with asyncpg_pool.acquire() as conn:
        await _insert_doc(conn, doc_id)
        try:
            result = await commit_staging(session_id, conn, neo4j_repo)
            assert result == 0
        finally:
            await _cleanup_pg(conn, session_id, doc_id, [])
