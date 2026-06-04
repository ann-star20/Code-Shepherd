"""
HITL (Human-in-the-Loop) 큐 관리 API

엔드포인트:
    GET  /hitl/queue                     대기 중인 HITL 항목 목록
    GET  /hitl/queue/{queue_id}          특정 항목 상세
    POST /hitl/queue/{queue_id}/approve  승인 (선택적 자동 재처리)
    POST /hitl/queue/{queue_id}/reject   거부
    POST /hitl/queue/{queue_id}/reprocess 재처리 (수정된 Markdown 주입 가능)
"""
from __future__ import annotations

import json
import logging
import os
from uuid import UUID

import asyncpg
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query
from pydantic import BaseModel

from common.harness import AgentHarness, create_db_pool
from common.trace import DocPipelineStage, new_pipeline_trace
from module_0_kms.storage import Storage, get_storage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hitl", tags=["HITL"])

# main.py lifespan에서 주입됨
_db_pool: asyncpg.Pool | None = None
_storage: Storage | None = None

ALLOWED_ROLES = {"senior", "admin"}


def _require_reviewer(x_reviewer_role: str | None) -> None:
    """X-Reviewer-Role 헤더가 senior 또는 admin인지 검증."""
    if not x_reviewer_role or x_reviewer_role.lower() not in ALLOWED_ROLES:
        raise HTTPException(
            status_code=403,
            detail=f"HITL 작업은 senior/admin 역할만 허용됩니다. 헤더: X-Reviewer-Role",
        )


async def _get_pool() -> asyncpg.Pool:
    global _db_pool
    if _db_pool is None:
        _db_pool = await create_db_pool()
    return _db_pool


# ---------------------------------------------------------------------------
# Pydantic 모델
# ---------------------------------------------------------------------------

class HitlQueueItem(BaseModel):
    queue_id: str
    doc_id: str
    stage: str
    reason: str
    quality_score: float | None = None
    issues: dict | list | None = None
    status: str
    reviewer_id: str | None = None
    review_note: str | None = None
    created_at: str
    # documents 테이블 JOIN 필드 (LEFT JOIN이므로 None 가능)
    original_filename: str | None = None
    file_type: str | None = None
    parser_used: str | None = None


class HitlQueuePageResponse(BaseModel):
    items: list[HitlQueueItem]
    total: int
    limit: int
    offset: int


class ApproveRequest(BaseModel):
    reviewer_id: str
    review_note: str | None = None
    auto_reprocess: bool = False


class RejectRequest(BaseModel):
    reviewer_id: str
    review_note: str


class ReprocessRequest(BaseModel):
    reviewer_id: str
    corrected_markdown: str | None = None
    skip_validation: bool = False


# ---------------------------------------------------------------------------
# 엔드포인트
# ---------------------------------------------------------------------------

@router.get("/queue", response_model=HitlQueuePageResponse)
async def list_hitl_queue(
    status: str = "pending",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> HitlQueuePageResponse:
    """HITL 큐 목록 조회 (페이지네이션 지원).

    ?status=pending|approved|rejected|reprocessing
    ?limit=20&offset=0
    """
    pool = await _get_pool()
    async with pool.acquire() as conn:
        total_row = await conn.fetchrow(
            "SELECT COUNT(*) AS total FROM hitl_queue WHERE status = $1",
            status,
        )
        rows = await conn.fetch(
            """
            SELECT hq.queue_id::text, hq.doc_id::text, hq.stage, hq.reason,
                   hq.quality_score, hq.issues, hq.status, hq.reviewer_id,
                   hq.review_note, hq.created_at::text,
                   d.original_filename, d.file_type, d.parser_used
            FROM hitl_queue hq
            LEFT JOIN documents d USING (doc_id)
            WHERE hq.status = $1
            ORDER BY hq.created_at DESC
            LIMIT $2 OFFSET $3
            """,
            status, limit, offset,
        )
    total = total_row["total"] if total_row else 0
    return HitlQueuePageResponse(
        items=[_row_to_item(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/queue/{queue_id}", response_model=HitlQueueItem)
async def get_hitl_item(queue_id: str) -> HitlQueueItem:
    """특정 HITL 항목 상세 조회."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT hq.queue_id::text, hq.doc_id::text, hq.stage, hq.reason,
                   hq.quality_score, hq.issues, hq.status, hq.reviewer_id,
                   hq.review_note, hq.created_at::text,
                   d.original_filename, d.file_type, d.parser_used
            FROM hitl_queue hq
            LEFT JOIN documents d USING (doc_id)
            WHERE hq.queue_id = $1
            """,
            UUID(queue_id),
        )
    if row is None:
        raise HTTPException(status_code=404, detail=f"HITL 항목 없음: {queue_id}")
    return _row_to_item(row)


@router.post("/queue/{queue_id}/approve")
async def approve_hitl(
    queue_id: str,
    body: ApproveRequest,
    background_tasks: BackgroundTasks,
    x_reviewer_role: str | None = Header(default=None),
) -> dict:
    """
    HITL 항목을 승인한다.
    auto_reprocess=True이면 저장된 Markdown으로 stage3부터 백그라운드 재처리.
    """
    _require_reviewer(x_reviewer_role)
    pool = await _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM hitl_queue WHERE queue_id = $1 AND status = 'pending'",
            UUID(queue_id),
        )
        if row is None:
            raise HTTPException(status_code=404, detail="대기 중인 HITL 항목 없음")

        await conn.execute(
            """
            UPDATE hitl_queue
            SET status = 'approved', reviewer_id = $1,
                review_note = $2, reviewed_at = NOW()
            WHERE queue_id = $3
            """,
            body.reviewer_id, body.review_note, UUID(queue_id),
        )
        await conn.execute(
            "UPDATE documents SET upload_status = 'approved' WHERE doc_id = $1",
            row["doc_id"],
        )

    if body.auto_reprocess:
        raw_issues = row["issues"] or {}
        issues = json.loads(raw_issues) if isinstance(raw_issues, str) else raw_issues
        background_tasks.add_task(
            _reprocess_document,
            doc_id=str(row["doc_id"]),
            stage=row["stage"],
            issues=issues,
        )
        return {
            "status": "approved",
            "message": "승인됨. 파이프라인 재처리를 백그라운드에서 시작합니다.",
        }

    return {
        "status": "approved",
        "message": "승인됨. 재처리하려면 /reprocess 엔드포인트를 호출하세요.",
    }


@router.post("/queue/{queue_id}/reject")
async def reject_hitl(
    queue_id: str,
    body: RejectRequest,
    x_reviewer_role: str | None = Header(default=None),
) -> dict:
    """HITL 항목을 거부한다. 문서 상태가 'rejected'로 변경된다."""
    _require_reviewer(x_reviewer_role)
    pool = await _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT doc_id FROM hitl_queue WHERE queue_id = $1 AND status = 'pending'",
            UUID(queue_id),
        )
        if row is None:
            raise HTTPException(status_code=404, detail="대기 중인 HITL 항목 없음")

        await conn.execute(
            """
            UPDATE hitl_queue
            SET status = 'rejected', reviewer_id = $1,
                review_note = $2, reviewed_at = NOW()
            WHERE queue_id = $3
            """,
            body.reviewer_id, body.review_note, UUID(queue_id),
        )
        await conn.execute(
            "UPDATE documents SET upload_status = 'rejected' WHERE doc_id = $1",
            row["doc_id"],
        )

    return {"status": "rejected", "message": "거부됨. 문서 처리가 중단되었습니다."}


@router.post("/queue/{queue_id}/reprocess", status_code=202)
async def reprocess_hitl(
    queue_id: str,
    body: ReprocessRequest,
    background_tasks: BackgroundTasks,
    x_reviewer_role: str | None = Header(default=None),
) -> dict:
    """
    HITL 항목을 재처리한다.
    corrected_markdown을 제공하면 그 내용으로 stage2부터 재실행.
    제공하지 않으면 저장된 Markdown으로 stage3부터 재실행.
    """
    _require_reviewer(x_reviewer_role)
    pool = await _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM hitl_queue WHERE queue_id = $1",
            UUID(queue_id),
        )
        if row is None:
            raise HTTPException(status_code=404, detail="HITL 항목 없음")

        await conn.execute(
            """
            UPDATE hitl_queue
            SET status = 'reprocessing', reviewer_id = $1, reviewed_at = NOW()
            WHERE queue_id = $2
            """,
            body.reviewer_id, UUID(queue_id),
        )

    raw_issues = row["issues"] or {}
    issues = json.loads(raw_issues) if isinstance(raw_issues, str) else raw_issues
    background_tasks.add_task(
        _reprocess_document,
        doc_id=str(row["doc_id"]),
        stage=row["stage"],
        issues=issues,
        corrected_markdown=body.corrected_markdown,
        skip_validation=body.skip_validation,
    )

    return {
        "status": "reprocessing",
        "message": "재처리가 백그라운드에서 시작됩니다.",
        "doc_id": str(row["doc_id"]),
    }


# ---------------------------------------------------------------------------
# KB Evolution — 카테고리 제안 / 적용 엔드포인트
# ---------------------------------------------------------------------------

async def suggest_category_for_hitl(queue_id: str) -> dict:
    """HITL 항목의 AI 카테고리 제안과 근거를 반환한다.

    hitl_queue.issues 에 저장된 category_reasoning / category_alternatives 를
    꺼내서 프론트엔드 KB Evolution UI에 전달한다.
    """
    pool = await _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT issues FROM hitl_queue WHERE queue_id = $1",
            UUID(queue_id),
        )
    if row is None:
        raise HTTPException(status_code=404, detail="HITL 항목 없음")

    raw_issues = row["issues"] or {}
    issues_data = json.loads(raw_issues) if isinstance(raw_issues, str) else raw_issues

    reasoning   = issues_data.get("category_reasoning", "")
    alternatives = issues_data.get("category_alternatives", [])
    proposed    = _extract_proposed_category(issues_data.get("issues", []))

    # 제안 목록: 새 카테고리 먼저, 기존 차선책 뒤에
    suggested = ([proposed] if proposed else []) + [
        a for a in alternatives if a != proposed
    ]

    return {
        "suggested":           suggested[:3],
        "reasoning":           reasoning,
        "category_reasoning":  reasoning,
        "alternatives":        alternatives,
        "category_alternatives": alternatives,
    }


def _extract_proposed_category(issues: list[str]) -> str:
    """issues 목록에서 '새 카테고리 제안: ...' 패턴으로 카테고리명을 추출한다."""
    for issue in issues:
        if "새 카테고리 제안:" in issue:
            # "새 카테고리 제안: 'NCS교육'" → "NCS교육"
            return issue.split("새 카테고리 제안:")[-1].strip().strip("'\"")
    return ""


async def get_hitl_markdown(queue_id: str) -> dict:
    """HITL 항목의 변환된 Markdown 내용을 반환한다.

    issues.markdown_storage_path → 없으면 markdown/{doc_id}/raw.md 폴백.
    """
    global _storage
    storage = _storage or get_storage()

    pool = await _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT issues, doc_id::text FROM hitl_queue WHERE queue_id = $1",
            UUID(queue_id),
        )
    if row is None:
        raise HTTPException(status_code=404, detail="HITL 항목 없음")

    raw_issues = row["issues"] or {}
    issues = json.loads(raw_issues) if isinstance(raw_issues, str) else raw_issues
    doc_id = row["doc_id"]

    markdown_path = (
        issues.get("markdown_storage_path")
        if isinstance(issues, dict)
        else None
    ) or f"markdown/{doc_id}/raw.md"

    try:
        raw = await storage.load(markdown_path)
        markdown = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Markdown 로드 실패: {exc}") from exc

    return {"markdown": markdown, "path": markdown_path}


@router.get("/queue/{queue_id}/markdown")
async def get_markdown_endpoint(queue_id: str) -> dict:
    """HITL 항목의 변환된 Markdown 내용 조회."""
    return await get_hitl_markdown(queue_id)


@router.get("/queue/{queue_id}/suggest-category")
async def suggest_category_endpoint(queue_id: str) -> dict:
    """KB Evolution — AI 카테고리 제안 조회."""
    return await suggest_category_for_hitl(queue_id)


async def apply_category_from_hitl(
    queue_id: str,
    category: str,
    description: str = "",
) -> None:
    """선택된 카테고리를 DB에 추가하고 파이프라인 재처리를 시작한다."""
    from module_0_kms.categories_db import add_category

    pool = await _get_pool()

    # 1. categories 테이블에 추가 (이미 있으면 무시)
    await add_category(pool, category, description)

    # 2. HITL 항목 조회
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM hitl_queue WHERE queue_id = $1",
            UUID(queue_id),
        )
        if row is None:
            raise HTTPException(status_code=404, detail="HITL 항목 없음")

        await conn.execute(
            """UPDATE hitl_queue
               SET status = 'approved', reviewed_at = NOW()
               WHERE queue_id = $1""",
            UUID(queue_id),
        )

    # 3. 파이프라인 재처리 (수정된 카테고리 적용)
    raw_issues = row["issues"] or {}
    issues = json.loads(raw_issues) if isinstance(raw_issues, str) else raw_issues

    await _reprocess_document(
        doc_id=str(row["doc_id"]),
        stage=row["stage"],
        issues=issues,
        corrected_category=category,
        skip_validation=True,
    )


class ApplyCategoryRequest(BaseModel):
    category: str
    description: str = ""
    reviewer_id: str = "admin"


@router.post("/queue/{queue_id}/apply-category", status_code=202)
async def apply_category_endpoint(
    queue_id: str,
    body: ApplyCategoryRequest,
    background_tasks: BackgroundTasks,
    x_reviewer_role: str | None = Header(default=None),
) -> dict:
    """KB Evolution — 카테고리 DB 추가 + 파이프라인 재시작."""
    _require_reviewer(x_reviewer_role)
    background_tasks.add_task(
        apply_category_from_hitl,
        queue_id=queue_id,
        category=body.category,
        description=body.description,
    )
    return {
        "status": "applying",
        "message": f"카테고리 '{body.category}' 추가 및 재처리를 시작합니다.",
    }


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------

def _row_to_item(row) -> HitlQueueItem:
    d = dict(row)
    # asyncpg가 JSONB를 dict로 반환하지만 string일 수도 있으므로 안전하게 처리
    issues = d.get("issues")
    if isinstance(issues, str):
        try:
            issues = json.loads(issues)
        except (json.JSONDecodeError, TypeError):
            issues = None
    d["issues"] = issues
    return HitlQueueItem(**d)


async def _reprocess_document(
    doc_id: str,
    stage: str,
    issues: dict,
    corrected_markdown: str | None = None,
    skip_validation: bool = False,
    corrected_category: str | None = None,
) -> None:
    """
    백그라운드 재처리.
    - corrected_markdown 제공 시: stage2(재검증) → stage3 → stage4 → stage5 → stage6
    - 제공 없이 skip_validation=True: stage3 → stage4 → stage5 → stage6
    - stage4 HITL인 경우: stage3부터 재실행
    """
    global _db_pool, _storage
    pool = _db_pool or await create_db_pool()
    storage = _storage or get_storage()

    # 재처리 시작 — DB에 상태를 즉시 업데이트해 프론트엔드 폴링에서 감지 가능하게 함
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE documents SET upload_status = 'reprocessing' WHERE doc_id = $1",
            UUID(doc_id),
        )

    # 저장된 Markdown 경로에서 로드
    markdown_path = issues.get("markdown_storage_path") if isinstance(issues, dict) else None

    # issues에 경로가 없으면 documents 테이블에서 직접 조회 (stage5b HITL 등 경로 미저장 케이스)
    if markdown_path is None:
        try:
            async with pool.acquire() as conn:
                doc_row = await conn.fetchrow(
                    "SELECT markdown_path FROM documents WHERE doc_id = $1",
                    UUID(doc_id),
                )
                if doc_row and doc_row["markdown_path"]:
                    markdown_path = doc_row["markdown_path"]
        except Exception as e:
            logger.warning(f"documents.markdown_path 조회 실패: {e}", extra={"doc_id": doc_id})

    # 표준 저장 패턴으로 최종 폴백 (Stage 1은 항상 이 경로에 저장)
    if markdown_path is None:
        markdown_path = f"markdown/{doc_id}/raw.md"
        logger.info(f"markdown_path 표준 경로 폴백: {markdown_path}", extra={"doc_id": doc_id})

    raw_markdown = corrected_markdown

    if raw_markdown is None and markdown_path:
        try:
            raw_content = await storage.load(markdown_path)
            raw_markdown = (
                raw_content.decode("utf-8") if isinstance(raw_content, bytes)
                else raw_content
            )
        except Exception as e:
            logger.error(
                f"Markdown 로드 실패 — 재처리 중단: {e}",
                extra={"doc_id": doc_id},
            )
            await _mark_reprocess_failed(pool, doc_id)
            return

    if raw_markdown is None:
        logger.error("재처리할 Markdown이 없음 — 재처리 중단", extra={"doc_id": doc_id})
        await _mark_reprocess_failed(pool, doc_id)
        return

    from module_0_kms.pipeline.models import make_reprocess_state
    from module_0_kms.pipeline.stage2_validate_agent import stage2_validate
    from module_0_kms.pipeline.stage3_chunk import stage3_chunk
    from module_0_kms.pipeline.stage4_chunk_validate import stage4_chunk_validate
    from module_0_kms.pipeline.stage5_metadata_agent import stage5_metadata
    from module_0_kms.pipeline.stage5b_metadata_validate_agent import stage5b_metadata_validate
    from module_0_kms.pipeline.stage6_store import stage6_store

    # corrected_markdown이 없으면 사람이 기존 Markdown을 승인한 것이므로 stage2 건너뜀
    start_validated = skip_validation or (corrected_markdown is None)

    state = make_reprocess_state(
        doc_id=doc_id,
        raw_markdown=raw_markdown,
        markdown_path=markdown_path,
        start_validated=start_validated,
    )

    # KB Evolution: 사람이 승인한 카테고리를 state에 직접 주입
    # → Stage 5가 다시 추론하지 않고 이 카테고리를 사용
    if corrected_category:
        if state.get("metadata") is None:
            state["metadata"] = {}
        state["metadata"]["category"] = corrected_category
        state["category_is_new"] = False   # 이제 사람이 승인한 카테고리 → 새것 아님
        state["category_reasoning"] = ""
        state["category_alternatives"] = []

    _doc_uuid = UUID(doc_id)

    _stage6_timeout = int(os.getenv("STAGE6_TIMEOUT_SECONDS", "900"))

    def _harness(pipeline_stage: DocPipelineStage, agent_name: str, timeout: int | None = None) -> AgentHarness:
        return AgentHarness(
            trace_id=new_pipeline_trace(pipeline_stage, doc_id=_doc_uuid),
            agent_name=agent_name,
            db_pool=pool,
            doc_id=_doc_uuid,
            timeout=timeout,
        )

    try:
        # Stage 2: 검증 (corrected_markdown 제공 시만)
        if not start_validated:
            async with _harness(DocPipelineStage.MARKDOWN_VALIDATE, "MarkdownValidateAgent") as h:
                result = await h.run(stage2_validate, state)
            state = {**state, **result}
            if state.get("hitl_required"):
                await _abort_reprocess_with_hitl(
                    pool, doc_id, "stage2_validate",
                    state.get("quality_issues") or [],
                )
                return
            if state.get("status") == "failed":
                await _mark_reprocess_failed(pool, doc_id)
                return

        # Stage 3: 청킹
        async with _harness(DocPipelineStage.CHUNKING, "ChunkingAgent") as h:
            result = await h.run(stage3_chunk, state)
        state = {**state, **result}
        if state.get("status") == "failed":
            return

        # Stage 4: Chunk 검증
        async with _harness(DocPipelineStage.CHUNK_VALIDATE, "ChunkValidateAgent") as h:
            result = await h.run(stage4_chunk_validate, state)
        state = {**state, **result}
        if not skip_validation and state.get("hitl_required"):
            await _abort_reprocess_with_hitl(
                pool, doc_id, "stage4_chunk_validate",
                state.get("chunk_validation_issues") or [],
            )
            return

        # Stage 5: 메타데이터 추출
        async with _harness(DocPipelineStage.METADATA_EXTRACT, "MetadataExtractAgent") as h:
            result = await h.run(stage5_metadata, state)
        state = {**state, **result}

        # Stage 5b: 메타데이터 검증
        async with _harness(DocPipelineStage.METADATA_VALIDATE, "MetadataValidateAgent") as h:
            result = await h.run(stage5b_metadata_validate, state)
        state = {**state, **result}
        if not skip_validation and state.get("hitl_required"):
            await _abort_reprocess_with_hitl(
                pool, doc_id, "stage5b_metadata_validate",
                state.get("metadata_issues") or [],
            )
            return

        # Stage 6: 저장 (임베딩 포함 — 대용량 문서 대응 전용 타임아웃 적용)
        async with _harness(DocPipelineStage.STORE_ROUTE, "StoreRouteAgent", timeout=_stage6_timeout) as h:
            result = await h.run(stage6_store, state, pool, storage)
        state = {**state, **result}

        logger.info(
            "재처리 완료",
            extra={"doc_id": doc_id, "status": state.get("status")},
        )

    except Exception as e:
        logger.error(
            f"재처리 중 예외 발생: {e}",
            extra={"doc_id": doc_id},
        )
        await _mark_reprocess_failed(pool, doc_id)


async def _mark_reprocess_failed(pool: asyncpg.Pool, doc_id: str) -> None:
    """재처리 실패 시 문서 상태 업데이트."""
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE documents SET upload_status = 'reprocess_failed' WHERE doc_id = $1",
                UUID(doc_id),
            )
    except Exception as e:
        logger.warning(f"재처리 실패 상태 업데이트 오류: {e}")


async def _enqueue_hitl_reprocess(
    pool: asyncpg.Pool,
    doc_id: str,
    stage: str,
    issues: list[str],
) -> None:
    """재처리 중 HITL 재트리거 시 hitl_queue에 새 항목을 삽입한다."""
    reason = ", ".join(issues) if issues else "재처리 중 검증 실패"
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO hitl_queue (doc_id, stage, reason, issues, status)
                VALUES ($1, $2, $3, $4::jsonb, 'pending')
                """,
                UUID(doc_id),
                stage,
                reason,
                json.dumps({"issues": issues}),
            )
        logger.info(
            "재처리 HITL 재등록",
            extra={"doc_id": doc_id, "stage": stage},
        )
    except Exception as e:
        logger.error(
            f"재처리 HITL hitl_queue INSERT 실패: {e}",
            extra={"doc_id": doc_id},
        )


async def _abort_reprocess_with_hitl(
    pool: asyncpg.Pool,
    doc_id: str,
    stage_name: str,
    issues: list[str],
) -> None:
    """재처리 중 HITL 재트리거 시 큐 등록 + 문서 상태를 hitl_pending으로 설정한다."""
    logger.warning(
        f"재처리 {stage_name} HITL 재트리거",
        extra={"doc_id": doc_id},
    )
    await _enqueue_hitl_reprocess(pool, doc_id, stage_name, issues)
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE documents SET upload_status = 'hitl_pending' WHERE doc_id = $1",
            UUID(doc_id),
        )
