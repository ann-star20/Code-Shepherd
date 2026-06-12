"""Staging Gate API 라우터 (PRD §11).

POST   /api/staging/{session_id}/approve
GET    /api/staging/{session_id}
POST   /api/staging/{session_id}/reject
GET    /api/staging/{session_id}/diff
PATCH  /api/staging/{session_id}/nodes/{node_id}
"""

import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
import asyncpg

from app.usecases.approve_staging import approve_staging
from app.usecases.exceptions import StagingConflictError


def _write_graph(session_id: str, doc_id: str):
    from app.worker.tasks import write_graph_task as _task
    return _task.delay(session_id=session_id, doc_id=doc_id)

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
    summary="개념 목록 조회 (기본: DRAFT, all_states=true 시 전체)",
    status_code=status.HTTP_200_OK,
)
async def list_draft(
    session_id: str,
    all_states: bool = False,
    conn: asyncpg.Connection = Depends(_get_conn),
) -> dict:
    if all_states:
        rows = await conn.fetch(
            """SELECT id, concept_json, state, created_at
               FROM staging_concepts
               WHERE session_id = $1::uuid
               ORDER BY id""",
            session_id,
        )
    else:
        rows = await conn.fetch(
            """SELECT id, concept_json, state, created_at
               FROM staging_concepts
               WHERE session_id = $1::uuid AND state = 'DRAFT'
               ORDER BY id""",
            session_id,
        )
    items = []
    for r in rows:
        raw = r["concept_json"]
        data = json.loads(raw) if isinstance(raw, str) else dict(raw)
        items.append({"id": str(r["id"]), "state": r["state"], "created_at": str(r["created_at"]), **data})
    return {"items": items}


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
        "DELETE FROM staging_concepts WHERE session_id = $1::uuid AND state = 'DRAFT'",
        session_id,
    )
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
        """SELECT state, count(*)::int AS cnt
           FROM staging_concepts
           WHERE session_id = $1::uuid
           GROUP BY state""",
        session_id,
    )
    counts = {r["state"].lower(): r["cnt"] for r in rows}
    return {
        "draft":     counts.get("draft", 0),
        "approved":  counts.get("approved", 0),
        "committed": counts.get("committed", 0),
    }


# ── POST /{session_id}/commit ─────────────────────────────────────────────────

@router.post(
    "/{session_id}/commit",
    summary="APPROVED → Neo4j 적재 트리거",
    status_code=status.HTTP_202_ACCEPTED,
)
async def commit_session(
    session_id: str,
    conn: asyncpg.Connection = Depends(_get_conn),
) -> dict:
    """APPROVED 항목을 Graph Writer Celery 태스크로 전달."""
    row = await conn.fetchrow(
        "SELECT doc_id FROM staging_concepts WHERE session_id = $1::uuid LIMIT 1",
        session_id,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
    doc_id = row["doc_id"]
    try:
        _write_graph(session_id=session_id, doc_id=doc_id)
    except Exception:
        pass
    return {"session_id": session_id, "doc_id": doc_id, "message": "그래프 적재 시작됨"}


# ── PATCH /{session_id}/nodes/{node_id} ───────────────────────────────────────

@router.patch(
    "/{session_id}/nodes/{node_id}",
    summary="개별 개념 상태 전환 (APPROVED/REJECTED)",
    status_code=status.HTTP_200_OK,
)
async def patch_node(
    session_id: str,
    node_id: int,
    target_state: Literal["APPROVED", "REJECTED"],
    conn: asyncpg.Connection = Depends(_get_conn),
) -> dict:
    result = await conn.execute(
        """UPDATE staging_concepts
           SET state = $1, updated_at = NOW()
           WHERE id = $2 AND session_id = $3::uuid""",
        target_state,
        node_id,
        session_id,
    )
    if result == "UPDATE 0":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")
    return {"id": node_id, "state": target_state}
