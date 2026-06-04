"""approve_staging 유스케이스 — DRAFT → APPROVED 단일 승인자 보장 (PRD §11).

SELECT FOR UPDATE SKIP LOCKED으로 동시 승인 요청 중 단 하나만 성공한다.
"""
import asyncpg

from app.usecases.exceptions import StagingConflictError


async def approve_staging(session_id: str, conn: asyncpg.Connection) -> int:
    """session_id의 모든 DRAFT 개념을 APPROVED로 전환한다.

    Returns:
        승인된 행 수.

    Raises:
        StagingConflictError: DRAFT 행이 없거나 다른 트랜잭션이 잠금 중.
    """
    async with conn.transaction():
        # SKIP LOCKED: 이미 잠긴 행은 건너뜀 → 동시 호출 시 두 번째는 0행 반환
        rows = await conn.fetch(
            """SELECT id FROM staging_concepts
               WHERE session_id = $1::uuid AND status = 'DRAFT'
               FOR UPDATE SKIP LOCKED""",
            session_id,
        )

        if not rows:
            raise StagingConflictError(
                f"No DRAFT rows available for session {session_id!r} "
                "(already approved or locked by concurrent request)"
            )

        row_ids = [r["id"] for r in rows]

        updated: int = await conn.fetchval(
            """WITH upd AS (
                   UPDATE staging_concepts
                   SET status      = 'APPROVED',
                       reviewed_at = NOW(),
                       updated_at  = NOW()
                   WHERE id = ANY($1)
                   RETURNING 1
               )
               SELECT count(*)::int FROM upd""",
            row_ids,
        )
        return updated or 0
