"""HITL 스테이징 검토 엔드포인트."""

from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import pg_dsn
from app.worker.tasks import write_graph_task

router = APIRouter(prefix="/api/staging", tags=["staging"])

_PG_DSN = pg_dsn()


@router.get("/{session_id}")
async def list_staging(session_id: str) -> list[dict[str, Any]]:
    """세션의 DRAFT/APPROVED staging 개념 목록."""
    conn = await asyncpg.connect(_PG_DSN)
    try:
        rows = await conn.fetch(
            "SELECT id::text, concept_json, state, infer_action, infer_confidence, "
            "       target_concept_name, score_jaro_winkler, score_name_vector, score_desc_vector "
            "FROM staging_concepts "
            "WHERE session_id = $1 AND state IN ('DRAFT', 'APPROVED') "
            "ORDER BY created_at",
            uuid.UUID(session_id),
        )
        return [dict(r) for r in rows]
    finally:
        await conn.close()


@router.post("/{staging_id}/approve", status_code=200)
async def approve(staging_id: str) -> dict[str, str]:
    """DRAFT -> APPROVED (SELECT FOR UPDATE SKIP LOCKED - 이중 승인 방지)."""
    conn = await asyncpg.connect(_PG_DSN)
    try:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT id, state FROM staging_concepts WHERE id = $1 FOR UPDATE SKIP LOCKED",
                uuid.UUID(staging_id),
            )
            if row is None:
                raise HTTPException(status_code=409, detail="이미 처리 중이거나 존재하지 않는 항목입니다")
            if row["state"] != "DRAFT":
                raise HTTPException(status_code=400, detail=f"현재 상태 '{row['state']}' - DRAFT만 승인 가능")
            await conn.execute(
                "UPDATE staging_concepts SET state = 'APPROVED', reviewed_at = now() WHERE id = $1",
                uuid.UUID(staging_id),
            )
        return {"id": staging_id, "state": "APPROVED"}
    finally:
        await conn.close()


@router.post("/{staging_id}/reject", status_code=200)
async def reject(staging_id: str) -> dict[str, str]:
    """DRAFT -> REJECTED."""
    conn = await asyncpg.connect(_PG_DSN)
    try:
        result = await conn.execute(
            "UPDATE staging_concepts SET state = 'REJECTED', reviewed_at = now() "
            "WHERE id = $1 AND state = 'DRAFT'",
            uuid.UUID(staging_id),
        )
        if result == "UPDATE 0":
            raise HTTPException(status_code=400, detail="DRAFT 상태가 아니거나 존재하지 않는 항목")
        return {"id": staging_id, "state": "REJECTED"}
    finally:
        await conn.close()


class CommitRequest(BaseModel):
    session_id: str


@router.post("/commit", status_code=202)
async def commit(body: CommitRequest) -> dict[str, Any]:
    """세션 APPROVED 항목 -> write_graph_task 트리거."""
    write_graph_task.apply_async(args=[body.session_id])
    return {"session_id": body.session_id, "status": "write_graph_triggered"}


@router.get("/{staging_id}/diff")
async def diff(staging_id: str) -> dict[str, Any]:
    """스테이징 항목 vs 기존 마스터 개념 차이 미리보기."""
    conn = await asyncpg.connect(_PG_DSN)
    try:
        row = await conn.fetchrow(
            "SELECT concept_json, infer_action, target_concept_name FROM staging_concepts WHERE id = $1",
            uuid.UUID(staging_id),
        )
        if row is None:
            raise HTTPException(status_code=404, detail="항목 없음")
        incoming = json.loads(row["concept_json"])
        existing = None
        if row["target_concept_name"]:
            master = await conn.fetchrow(
                "SELECT concept_name, aliases, description_ko, severity, domains "
                "FROM concepts WHERE concept_name = $1",
                row["target_concept_name"],
            )
            if master:
                existing = dict(master)
        return {
            "incoming": incoming,
            "existing": existing,
            "infer_action": row["infer_action"],
        }
    finally:
        await conn.close()
