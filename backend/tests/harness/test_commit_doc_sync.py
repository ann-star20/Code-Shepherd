"""G13: commit_staging 후 knowledge_document.state 동기화 테스트 (PRD 규칙④).

SDD 스펙:
  - commit_staging 완료 후 해당 doc_id의 knowledge_document.state = 'COMMITTED'
  - knowledge_document 상태 업데이트는 concepts INSERT와 동일 트랜잭션

T_dc_01: APPROVED staging → commit_staging → knowledge_document.state = 'COMMITTED'
T_dc_02: APPROVED 0건 → knowledge_document 상태 변경 없음
"""

import json
import uuid
import pytest

from app.usecases.commit_staging import commit_staging


def _cj(name: str) -> str:
    return json.dumps(
        {
            "concept_name": name,
            "domains": ["security"],
            "severity": "high",
            "description_ko": "테스트",
            "aliases": [],
        }
    )


async def _insert_doc(conn, doc_id: str, state: str = "EXTRACTED") -> None:
    await conn.execute(
        "INSERT INTO knowledge_document (doc_id, source_prefix, original_url, content_hash, state) "
        "VALUES ($1,'EXT','https://example.com/doc-sync-test','abcd1234',$2) ON CONFLICT DO NOTHING",
        doc_id,
        state,
    )


async def _insert_approved(conn, session_id: str, doc_id: str, name: str) -> None:
    await conn.execute(
        """INSERT INTO staging_concepts
           (session_id, doc_id, concept_json, state, known_domains, unknown_domains)
           VALUES ($1::uuid, $2, $3::jsonb, 'APPROVED', $4, '{}')""",
        session_id,
        doc_id,
        _cj(name),
        ["security"],
    )


async def _cleanup(
    conn, session_id: str, doc_id: str, concept_names: list[str]
) -> None:
    await conn.execute(
        "DELETE FROM staging_concepts WHERE session_id=$1::uuid", session_id
    )
    if concept_names:
        await conn.execute(
            "DELETE FROM concepts WHERE concept_name=ANY($1)", concept_names
        )
    await conn.execute("DELETE FROM knowledge_document WHERE doc_id=$1", doc_id)


# ── T_dc_01 ───────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_dc_01_commit_updates_document_state(asyncpg_pool, async_neo4j_driver):
    """Arrange: EXTRACTED 상태 document + 1건 APPROVED staging.
    Act: commit_staging.
    Assert: knowledge_document.state == 'COMMITTED'.
    """
    session_id = str(uuid.uuid4())
    doc_id = f"EXT_dc_{uuid.uuid4().hex[:8]}"
    name = f"XSS_dc_{uuid.uuid4().hex[:6]}"

    async with asyncpg_pool.acquire() as conn:
        await _insert_doc(conn, doc_id, state="EXTRACTED")
        await _insert_approved(conn, session_id, doc_id, name)
        try:
            count = await commit_staging(session_id, conn, async_neo4j_driver)
            assert count == 1

            doc_state = await conn.fetchval(
                "SELECT state FROM knowledge_document WHERE doc_id=$1", doc_id
            )
            assert (
                doc_state == "COMMITTED"
            ), f"knowledge_document.state={doc_state!r}, 'COMMITTED' 기대"
        finally:
            await _cleanup(conn, session_id, doc_id, [name])

    async with async_neo4j_driver.session() as s:
        await s.run("MATCH (c:Concept {name:$n}) DETACH DELETE c", n=name)


# ── T_dc_02 ───────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_dc_02_zero_approved_no_document_change(asyncpg_pool, async_neo4j_driver):
    """Arrange: document PENDING, APPROVED staging 없음.
    Act: commit_staging (0건 반환).
    Assert: knowledge_document.state 변경 없음 (여전히 PENDING).
    """
    session_id = str(uuid.uuid4())
    doc_id = f"EXT_dc_{uuid.uuid4().hex[:8]}"

    async with asyncpg_pool.acquire() as conn:
        await _insert_doc(conn, doc_id, state="PENDING")
        try:
            count = await commit_staging(session_id, conn, async_neo4j_driver)
            assert count == 0

            doc_state = await conn.fetchval(
                "SELECT state FROM knowledge_document WHERE doc_id=$1", doc_id
            )
            assert doc_state == "PENDING"
        finally:
            await conn.execute("DELETE FROM knowledge_document WHERE doc_id=$1", doc_id)
