"""approve_staging 유스케이스 — DRAFT → APPROVED 단일 승인자 보장 (PRD §11).

SELECT FOR UPDATE SKIP LOCKED으로 동시 승인 요청 중 단 하나만 성공한다.
"""

import asyncpg

from app.usecases.exceptions import StagingConflictError


async def approve_staging(session_id: str, conn: asyncpg.Connection) -> int:
    async with conn.transaction():
        rows = await conn.fetch(
            """SELECT id FROM staging_concepts
               WHERE session_id = $1::uuid AND state = 'DRAFT'
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
                   SET state       = 'APPROVED',
                       reviewed_at = NOW()
                   WHERE id = ANY($1)
                   RETURNING 1
               )
               SELECT count(*)::int FROM upd""",
            row_ids,
        )
        return updated or 0
