"""HITL 스테이징 검토 엔드포인트."""

from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg
from fastapi import APIRouter, HTTPException

from app.core.config import pg_dsn
from app.worker.tasks import write_graph_task

router = APIRouter(prefix="/staging", tags=["staging"])

_PG_DSN = pg_dsn()

_MERGE_PENDING_ACTIONS = {"MERGE", "RELATED_TO"}


@router.get("/{session_id}")
async def list_staging(session_id: str) -> dict[str, list[dict[str, Any]]]:
    """세션의 DRAFT/APPROVED staging 개념 목록 - GraphNode 형태."""
    conn = await asyncpg.connect(_PG_DSN)
    try:
        rows = await conn.fetch(
            "SELECT id::text AS staging_id, concept_json, state, infer_action, infer_confidence, "
            "       target_concept_name "
            "FROM staging_concepts "
            "WHERE session_id = $1 AND state IN ('DRAFT', 'APPROVED') "
            "ORDER BY created_at",
            uuid.UUID(session_id),
        )
        items = [_to_graph_node(row) for row in rows]
        return {"items": items}
    finally:
        await conn.close()


def _to_graph_node(row: Any) -> dict[str, Any]:
    concept_json = row["concept_json"]
    concept = json.loads(concept_json) if isinstance(concept_json, str) else concept_json
    infer_action = row["infer_action"]
    return {
        "id": concept.get("concept_name"),
        "name": concept.get("concept_name"),
        "status": "MERGE_PENDING" if infer_action in _MERGE_PENDING_ACTIONS else "DRAFT",
        "domains": concept.get("domains", []),
        "infer_action": infer_action,
        "infer_confidence": row["infer_confidence"],
        "target_concept_name": row["target_concept_name"],
        "cwe_id": concept.get("cwe_id"),
        "owasp_id": concept.get("owasp_id"),
        "severity": concept.get("severity"),
        "description_ko": concept.get("description_ko"),
        "aliases": concept.get("aliases", []),
        "mechanisms": concept.get("mechanism", []),
        "staging_id": row["staging_id"],
        "state": row["state"],
    }


@router.post("/{id}/approve", status_code=200)
async def approve(id: str) -> dict[str, Any]:
    """단일 항목(staging_id) DRAFT -> APPROVED 또는 세션(session_id) 전체 일괄 승인."""
    item_id = uuid.UUID(id)
    conn = await asyncpg.connect(_PG_DSN)
    try:
        exists = await conn.fetchval("SELECT 1 FROM staging_concepts WHERE id = $1", item_id)
        if exists:
            return await _approve_single(conn, id, item_id)
        approved = await conn.fetchval(
            "WITH updated AS ("
            "    UPDATE staging_concepts SET state = 'APPROVED', reviewed_at = now() "
            "    WHERE session_id = $1 AND state = 'DRAFT' RETURNING 1"
            ") SELECT count(*) FROM updated",
            item_id,
        )
        return {"session_id": id, "approved": approved}
    finally:
        await conn.close()


async def _approve_single(conn: Any, staging_id: str, item_id: uuid.UUID) -> dict[str, str]:
    """단일 항목 DRAFT -> APPROVED (SELECT FOR UPDATE SKIP LOCKED - 이중 승인 방지)."""
    async with conn.transaction():
        row = await conn.fetchrow(
            "SELECT id, state FROM staging_concepts WHERE id = $1 FOR UPDATE SKIP LOCKED",
            item_id,
        )
        if row is None:
            raise HTTPException(status_code=409, detail="이미 처리 중이거나 존재하지 않는 항목입니다")
        if row["state"] != "DRAFT":
            raise HTTPException(status_code=400, detail=f"현재 상태 '{row['state']}' - DRAFT만 승인 가능")
        await conn.execute(
            "UPDATE staging_concepts SET state = 'APPROVED', reviewed_at = now() WHERE id = $1",
            item_id,
        )
    return {"id": staging_id, "state": "APPROVED"}


@router.post("/{id}/reject", status_code=200)
async def reject(id: str) -> dict[str, Any]:
    """단일 항목(staging_id) DRAFT -> REJECTED 또는 세션(session_id) 전체 일괄 거부."""
    item_id = uuid.UUID(id)
    conn = await asyncpg.connect(_PG_DSN)
    try:
        exists = await conn.fetchval("SELECT 1 FROM staging_concepts WHERE id = $1", item_id)
        if exists:
            result = await conn.execute(
                "UPDATE staging_concepts SET state = 'REJECTED', reviewed_at = now() "
                "WHERE id = $1 AND state = 'DRAFT'",
                item_id,
            )
            if result == "UPDATE 0":
                raise HTTPException(status_code=400, detail="DRAFT 상태가 아니거나 존재하지 않는 항목")
            return {"id": id, "state": "REJECTED"}
        rejected = await conn.fetchval(
            "WITH updated AS ("
            "    UPDATE staging_concepts SET state = 'REJECTED', reviewed_at = now() "
            "    WHERE session_id = $1 AND state = 'DRAFT' RETURNING 1"
            ") SELECT count(*) FROM updated",
            item_id,
        )
        await conn.execute(
            "UPDATE knowledge_documents SET state = 'FAILED', updated_at = now() WHERE session_id = $1",
            id,
        )
        return {"session_id": id, "rejected": rejected}
    finally:
        await conn.close()


@router.post("/{session_id}/commit", status_code=202)
async def commit(session_id: str) -> dict[str, Any]:
    """세션 APPROVED 항목 -> write_graph_task 트리거."""
    write_graph_task.apply_async(args=[session_id])
    return {"session_id": session_id, "status": "write_graph_triggered"}


@router.get("/{session_id}/diff")
async def diff(session_id: str) -> dict[str, int]:
    """세션 staging 항목 상태별 집계 (DiffSummary)."""
    conn = await asyncpg.connect(_PG_DSN)
    try:
        rows = await conn.fetch(
            "SELECT state, count(*) AS cnt FROM staging_concepts WHERE session_id = $1 GROUP BY state",
            uuid.UUID(session_id),
        )
        counts = {row["state"]: row["cnt"] for row in rows}
        return {
            "draft": counts.get("DRAFT", 0),
            "approved": counts.get("APPROVED", 0),
            "committed": counts.get("COMMITTED", 0),
        }
    finally:
        await conn.close()
