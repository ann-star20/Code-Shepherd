"""Staging Gate API 라우터 (PRD §11).

POST   /api/staging/{session_id}/approve
GET    /api/staging/{session_id}
POST   /api/staging/{session_id}/reject
GET    /api/staging/{session_id}/diff
PATCH  /api/staging/{session_id}/nodes/{node_id}
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
import asyncpg

from app.usecases.approve_staging import approve_staging
from app.usecases.exceptions import StagingConflictError

router = APIRouter(prefix="/api/staging", tags=["staging"])


async def _get_conn() -> asyncpg.Connection:
    """asyncpg 연결 의존성 — Phase 2에서 lifespan pool로 교체."""
    raise NotImplementedError("DB pool not configured; wire in app startup")


# ── POST /{session_id}/approve ────────────────────────────────────────────────

@router.post(
    "/{session_id}/approve",
    summary="DRAFT 개념 일괄 승인",
    status_code=status.HTTP_200_OK,
)
async def approve_session(
    session_id: str,
    conn: asyncpg.Connection = Depends(_get_conn),
) -> dict:
    try:
        count = await approve_staging(session_id, conn)
        return {"approved": count}
    except StagingConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


# ── GET /{session_id} ─────────────────────────────────────────────────────────

@router.get(
    "/{session_id}",
    summary="DRAFT 개념 목록 조회",
    status_code=status.HTTP_200_OK,
)
async def list_draft(
    session_id: str,
    conn: asyncpg.Connection = Depends(_get_conn),
) -> dict:
    rows = await conn.fetch(
        """SELECT id, concept_name, concept_domain, severity, description_ko,
                  concept_type, cwe_id, status, created_at
           FROM staging_concepts
           WHERE session_id = $1::uuid AND status = 'DRAFT'
           ORDER BY id""",
        session_id,
    )
    return {"items": [dict(r) for r in rows]}


# ── POST /{session_id}/reject ─────────────────────────────────────────────────

@router.post(
    "/{session_id}/reject",
    summary="DRAFT 개념 전체 삭제",
    status_code=status.HTTP_200_OK,
)
async def reject_session(
    session_id: str,
    conn: asyncpg.Connection = Depends(_get_conn),
) -> dict:
    result = await conn.execute(
        "DELETE FROM staging_concepts WHERE session_id = $1::uuid AND status = 'DRAFT'",
        session_id,
    )
    # asyncpg execute returns "DELETE N"
    n = int(result.split()[-1])
    return {"rejected": n}


# ── GET /{session_id}/diff ────────────────────────────────────────────────────

@router.get(
    "/{session_id}/diff",
    summary="세션 내 상태별 카운트",
    status_code=status.HTTP_200_OK,
)
async def diff_session(
    session_id: str,
    conn: asyncpg.Connection = Depends(_get_conn),
) -> dict:
    rows = await conn.fetch(
        """SELECT status, count(*)::int AS cnt
           FROM staging_concepts
           WHERE session_id = $1::uuid
           GROUP BY status""",
        session_id,
    )
    counts = {r["status"].lower(): r["cnt"] for r in rows}
    return {
        "draft":     counts.get("draft", 0),
        "approved":  counts.get("approved", 0),
        "committed": counts.get("committed", 0),
    }


# ── PATCH /{session_id}/nodes/{node_id} ───────────────────────────────────────

@router.patch(
    "/{session_id}/nodes/{node_id}",
    summary="개별 개념 상태 전환 (APPROVED/REJECTED)",
    status_code=status.HTTP_200_OK,
)
async def patch_node(
    session_id: str,
    node_id: int,
    target_status: Literal["APPROVED", "REJECTED"],
    conn: asyncpg.Connection = Depends(_get_conn),
) -> dict:
    result = await conn.execute(
        """UPDATE staging_concepts
           SET status = $1, updated_at = NOW()
           WHERE id = $2 AND session_id = $3::uuid""",
        target_status,
        node_id,
        session_id,
    )
    if result == "UPDATE 0":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")
    return {"id": node_id, "status": target_status}
