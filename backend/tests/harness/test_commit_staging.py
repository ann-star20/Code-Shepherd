"""G9: commit_staging usecase 통합 테스트."""

import uuid
import pytest

from app.usecases.commit_staging import commit_staging


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _uid(base: str) -> str:
    return f"{base}_{uuid.uuid4().hex[:6]}"


async def _insert_doc(conn, doc_id: str) -> None:
    await conn.execute(
        "INSERT INTO documents (doc_id, url) VALUES ($1, $2) ON CONFLICT DO NOTHING",
        doc_id, "https://example.com/commit-test",
    )


async def _insert_approved(conn, session_id: str, doc_id: str, name: str) -> None:
    await conn.execute(
        """INSERT INTO staging_concepts
           (session_id, doc_id, concept_name, concept_domain, severity, description_ko,
            aliases, security_mechanisms, affected_components, config_properties, status)
           VALUES ($1::uuid, $2, $3, 'security', 'high', '테스트', '[]', '[]', '[]', '[]', 'APPROVED')""",
        session_id, doc_id, name,
    )


async def _cleanup_pg(conn, session_id: str, doc_id: str, concept_names: list[str]) -> None:
    await conn.execute(
        "DELETE FROM staging_concepts WHERE session_id = $1::uuid", session_id
    )
    if concept_names:
        await conn.execute(
            "DELETE FROM concepts WHERE concept_name = ANY($1)", concept_names
        )
    await conn.execute("DELETE FROM documents WHERE doc_id = $1", doc_id)


async def _cleanup_neo4j(driver, names: list[str]) -> None:
    async with driver.session() as s:
        await s.run(
            "UNWIND $names AS n MATCH (c:Concept {name: n}) DETACH DELETE c",
            names=names,
        )


# ── T_commit_writes_concepts ──────────────────────────────────────────────────

@pytest.mark.anyio
async def test_commit_writes_concepts(asyncpg_pool, async_neo4j_driver):
    """2행 APPROVED → commit_staging → concepts 테이블 2행."""
    session_id = str(uuid.uuid4())
    doc_id = f"EXT_cs_{uuid.uuid4().hex[:8]}"
    names = [_uid("XSS"), _uid("SQLI")]

    async with asyncpg_pool.acquire() as conn:
        await _insert_doc(conn, doc_id)
        for n in names:
            await _insert_approved(conn, session_id, doc_id, n)
        try:
            count = await commit_staging(session_id, conn, async_neo4j_driver)
            assert count == 2

            rows = await conn.fetch(
                "SELECT concept_name FROM concepts WHERE concept_name = ANY($1)", names
            )
            assert len(rows) == 2
        finally:
            await _cleanup_pg(conn, session_id, doc_id, names)
    await _cleanup_neo4j(async_neo4j_driver, names)


# ── T_commit_status_committed ─────────────────────────────────────────────────

@pytest.mark.anyio
async def test_commit_status_committed(asyncpg_pool, async_neo4j_driver):
    """2행 APPROVED → commit_staging → staging 모두 COMMITTED."""
    session_id = str(uuid.uuid4())
    doc_id = f"EXT_cs_{uuid.uuid4().hex[:8]}"
    names = [_uid("XSS"), _uid("SQLI")]

    async with asyncpg_pool.acquire() as conn:
        await _insert_doc(conn, doc_id)
        for n in names:
            await _insert_approved(conn, session_id, doc_id, n)
        try:
            await commit_staging(session_id, conn, async_neo4j_driver)

            statuses = await conn.fetch(
                "SELECT status FROM staging_concepts WHERE session_id = $1::uuid",
                session_id,
            )
            assert all(r["status"] == "COMMITTED" for r in statuses)
        finally:
            await _cleanup_pg(conn, session_id, doc_id, names)
    await _cleanup_neo4j(async_neo4j_driver, names)


# ── T_commit_neo4j ────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_commit_neo4j(asyncpg_pool, async_neo4j_driver):
    """XSS APPROVED → commit_staging → Neo4j Concept 존재."""
    session_id = str(uuid.uuid4())
    doc_id = f"EXT_cs_{uuid.uuid4().hex[:8]}"
    name = _uid("XSS")

    async with asyncpg_pool.acquire() as conn:
        await _insert_doc(conn, doc_id)
        await _insert_approved(conn, session_id, doc_id, name)
        try:
            await commit_staging(session_id, conn, async_neo4j_driver)
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


# ── T_commit_zero ─────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_commit_zero(asyncpg_pool, async_neo4j_driver):
    """0행 APPROVED → return 0, 예외 없음."""
    session_id = str(uuid.uuid4())
    doc_id = f"EXT_cs_{uuid.uuid4().hex[:8]}"

    async with asyncpg_pool.acquire() as conn:
        await _insert_doc(conn, doc_id)
        try:
            result = await commit_staging(session_id, conn, async_neo4j_driver)
            assert result == 0
        finally:
            await _cleanup_pg(conn, session_id, doc_id, [])
