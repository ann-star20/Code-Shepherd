"""Staging Gate API 라우터 (PRD §11).

POST /api/staging/{session_id}/approve
"""

from fastapi import APIRouter, Depends, HTTPException, status
import asyncpg

from app.usecases.approve_staging import approve_staging
from app.usecases.exceptions import StagingConflictError

router = APIRouter(prefix="/api/staging", tags=["staging"])


async def _get_conn() -> asyncpg.Connection:
    """asyncpg 연결 의존성 — Phase 2에서 lifespan pool로 교체."""
    raise NotImplementedError("DB pool not configured; wire in app startup")


@router.post(
    "/{session_id}/approve",
    summary="DRAFT 개념 일괄 승인",
    status_code=status.HTTP_200_OK,
)
async def approve_session(
    session_id: str,
    conn: asyncpg.Connection = Depends(_get_conn),
) -> dict:
    """session_id의 모든 DRAFT 스테이징 개념을 APPROVED로 전환한다.

    Returns:
        {"approved": int}
    """
    try:
        count = await approve_staging(session_id, conn)
        return {"approved": count}
    except StagingConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
