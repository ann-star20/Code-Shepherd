"""E1 통합 테스트 — approve_staging + SELECT FOR UPDATE SKIP LOCKED.

T06: 동시 approve 요청 → 단 하나만 성공, 나머지는 StagingConflictError
"""

import asyncio
import json
import uuid
import pytest

from app.usecases.approve_staging import approve_staging
from app.usecases.exceptions import StagingConflictError


# ── 테스트 헬퍼 ───────────────────────────────────────────────────────────


async def _setup_session(conn, session_id: str, n_concepts: int = 3) -> str:
    """테스트용 document + staging_concepts(DRAFT) 행 삽입."""
    doc_id = f"EXT_test-staging_{uuid.uuid4().hex[:8]}"

    await conn.execute(
        "INSERT INTO knowledge_document (doc_id, source_prefix, original_url, content_hash) "
        "VALUES ($1,'EXT','https://example.com/staging-test','abcd1234') ON CONFLICT DO NOTHING",
        doc_id,
    )
    for i in range(n_concepts):
        name = f"TestConcept_{i}_{uuid.uuid4().hex[:4]}"
        cj = json.dumps({
            "concept_name": name,
            "domains": ["security"],
            "severity": "high",
            "description_ko": "테스트 개념",
            "aliases": [],
        })
        await conn.execute(
            """INSERT INTO staging_concepts
               (session_id, doc_id, concept_json, state, known_domains, unknown_domains)
               VALUES ($1::uuid, $2, $3::jsonb, 'DRAFT', $4, '{}')""",
            session_id,
            doc_id,
            cj,
            ["security"],
        )
    return doc_id


async def _cleanup_session(conn, session_id: str, doc_id: str) -> None:
    """테스트 데이터 정리."""
    await conn.execute(
        "DELETE FROM staging_concepts WHERE session_id = $1::uuid", session_id
    )
    await conn.execute("DELETE FROM knowledge_document WHERE doc_id = $1", doc_id)


# ── T06: 레이스 컨디션 — 단일 승인자 보장 ────────────────────────────────


@pytest.mark.anyio
async def test_T06_concurrent_approve_single_winner(asyncpg_pool):
    """Arrange: 3개 DRAFT 개념이 있는 세션.
    Act: asyncio.gather로 동시에 두 번 approve_staging 호출 (각 별도 커넥션).
    Assert: 정확히 1개 성공(int 반환), 1개 StagingConflictError 발생.
    """
    session_id = str(uuid.uuid4())
    doc_id = None

    async with asyncpg_pool.acquire() as setup_conn:
        doc_id = await _setup_session(setup_conn, session_id, n_concepts=3)

    try:
        async with asyncpg_pool.acquire() as conn1, asyncpg_pool.acquire() as conn2:
            results = await asyncio.gather(
                approve_staging(session_id, conn1),
                approve_staging(session_id, conn2),
                return_exceptions=True,
            )

        successes = [r for r in results if isinstance(r, int)]
        conflicts = [r for r in results if isinstance(r, StagingConflictError)]

        assert (
            len(successes) == 1
        ), f"승인 성공이 {len(successes)}개 — 정확히 1개여야 함"
        assert (
            len(conflicts) == 1
        ), f"StagingConflictError가 {len(conflicts)}개 — 정확히 1개여야 함"
        assert successes[0] == 3, f"승인된 행이 {successes[0]}개 — 3개여야 함"

    finally:
        if doc_id:
            async with asyncpg_pool.acquire() as cleanup_conn:
                await _cleanup_session(cleanup_conn, session_id, doc_id)


@pytest.mark.anyio
async def test_T06_approve_empty_session_raises_conflict(asyncpg_pool):
    """Arrange: 존재하지 않는 session_id.
    Act: approve_staging 단독 호출.
    Assert: StagingConflictError 발생 (DRAFT 행 없음).
    """
    fake_session = str(uuid.uuid4())

    with pytest.raises(StagingConflictError):
        async with asyncpg_pool.acquire() as conn:
            await approve_staging(fake_session, conn)


@pytest.mark.anyio
async def test_T06_approve_idempotency_second_call_fails(asyncpg_pool):
    """Arrange: 1회 승인 완료된 세션.
    Act: 동일 세션 재승인 시도.
    Assert: 2회차는 StagingConflictError (DRAFT 행 없음 — 이미 APPROVED).
    """
    session_id = str(uuid.uuid4())
    doc_id = None

    async with asyncpg_pool.acquire() as setup_conn:
        doc_id = await _setup_session(setup_conn, session_id, n_concepts=2)

    try:
        async with asyncpg_pool.acquire() as conn:
            count = await approve_staging(session_id, conn)
        assert count == 2

        with pytest.raises(StagingConflictError):
            async with asyncpg_pool.acquire() as conn:
                await approve_staging(session_id, conn)

    finally:
        if doc_id:
            async with asyncpg_pool.acquire() as cleanup_conn:
                await _cleanup_session(cleanup_conn, session_id, doc_id)
