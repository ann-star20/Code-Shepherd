"""
HITL (Human-in-the-Loop) 큐 관리 API — SQLAlchemy async 버전

엔드포인트:
    GET  /hitl/queue                              대기 중인 HITL 항목 목록
    GET  /hitl/queue/{queue_id}                   특정 항목 상세
    POST /hitl/queue/{queue_id}/approve           승인 (선택적 자동 재처리)
    POST /hitl/queue/{queue_id}/reject            거부
    POST /hitl/queue/{queue_id}/reprocess         재처리 (수정된 Markdown 주입 가능)
    GET  /hitl/queue/{queue_id}/markdown          변환된 Markdown 반환
    GET  /hitl/queue/{queue_id}/page-images       파싱 페이지 이미지 목록
    GET  /hitl/queue/{queue_id}/page/{page_num}   특정 페이지 이미지 바이트 반환
    GET  /hitl/queue/{queue_id}/suggest-category  AI 카테고리 제안
    POST /hitl/queue/{queue_id}/apply-category    KB Evolution 카테고리 추가 + 재처리
"""

from __future__ import annotations

import json
import logging
import os
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.harness import AgentHarness
from shared.trace import DocPipelineStage, new_pipeline_trace
from app.storage import Storage, get_storage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hitl", tags=["HITL"])

# main.py lifespan에서 주입됨
_db_session_factory: async_sessionmaker[AsyncSession] | None = None
_storage: Storage | None = None

ALLOWED_ROLES = {"senior", "admin"}


def _require_reviewer(x_reviewer_role: str | None) -> None:
    """X-Reviewer-Role 헤더가 senior 또는 admin인지 검증."""
    if not x_reviewer_role or x_reviewer_role.lower() not in ALLOWED_ROLES:
        raise HTTPException(
            status_code=403,
            detail="HITL 작업은 senior/admin 역할만 허용됩니다. 헤더: X-Reviewer-Role",
        )


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _db_session_factory is None:
        raise RuntimeError("DB session factory가 초기화되지 않았습니다. lifespan을 확인하세요.")
    return _db_session_factory


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


class ApplyCategoryRequest(BaseModel):
    category: str
    description: str = ""
    reviewer_id: str = "admin"


# ---------------------------------------------------------------------------
# 엔드포인트
# ---------------------------------------------------------------------------

@router.get("/queue", response_model=HitlQueuePageResponse)
async def list_hitl_queue(
    status: str = "pending",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> HitlQueuePageResponse:
    """HITL 큐 목록 조회 (페이지네이션 지원)."""
    session_factory = _get_session_factory()
    async with session_factory() as session:
        count_result = await session.execute(
            text("SELECT COUNT(*) AS total FROM hitl_queue WHERE status = :status"),
            {"status": status},
        )
        count_row = count_result.mappings().fetchone()

        rows_result = await session.execute(
            text("""
                SELECT hq.queue_id::text, hq.doc_id::text, hq.stage, hq.reason,
                       hq.quality_score, hq.issues, hq.status, hq.reviewer_id,
                       hq.review_note, hq.created_at::text,
                       d.original_filename, d.file_type, d.parser_used
                FROM hitl_queue hq
                LEFT JOIN documents d USING (doc_id)
                WHERE hq.status = :status
                ORDER BY hq.created_at DESC
                LIMIT :limit OFFSET :offset
            """),
            {"status": status, "limit": limit, "offset": offset},
        )
        rows = rows_result.mappings().fetchall()

    total = count_row["total"] if count_row else 0
    return HitlQueuePageResponse(
        items=[_row_to_item(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/queue/{queue_id}", response_model=HitlQueueItem)
async def get_hitl_item(queue_id: str) -> HitlQueueItem:
    """특정 HITL 항목 상세 조회."""
    session_factory = _get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            text("""
                SELECT hq.queue_id::text, hq.doc_id::text, hq.stage, hq.reason,
                       hq.quality_score, hq.issues, hq.status, hq.reviewer_id,
                       hq.review_note, hq.created_at::text,
                       d.original_filename, d.file_type, d.parser_used
                FROM hitl_queue hq
                LEFT JOIN documents d USING (doc_id)
                WHERE hq.queue_id = :queue_id
            """),
            {"queue_id": str(UUID(queue_id))},
        )
        row = result.mappings().fetchone()
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
    session_factory = _get_session_factory()

    async with session_factory() as session:
        pending_result = await session.execute(
            text("SELECT * FROM hitl_queue WHERE queue_id = :queue_id AND status = 'pending'"),
            {"queue_id": str(UUID(queue_id))},
        )
        row = pending_result.mappings().fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="대기 중인 HITL 항목 없음")

        await session.execute(
            text("""
                UPDATE hitl_queue
                SET status = 'approved', reviewer_id = :reviewer_id,
                    review_note = :review_note, reviewed_at = NOW()
                WHERE queue_id = :queue_id
            """),
            {
                "reviewer_id": body.reviewer_id,
                "review_note": body.review_note,
                "queue_id": str(UUID(queue_id)),
            },
        )
        await session.execute(
            text("UPDATE documents SET upload_status = 'approved' WHERE doc_id = :doc_id"),
            {"doc_id": str(row["doc_id"])},
        )
        await session.commit()

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
    """HITL 항목을 거부한다. 문서 상태가 'rejected'로 변경되고 파생 GCS 파일이 삭제된다.

    삭제 대상: images/{doc_id}/, markdown/{doc_id}/
    보존 대상: originals/{doc_id}.* (재처리 가능성), documents 레코드 (감사 이력)
    """
    _require_reviewer(x_reviewer_role)
    session_factory = _get_session_factory()

    async with session_factory() as session:
        pending_result = await session.execute(
            text("SELECT doc_id FROM hitl_queue WHERE queue_id = :queue_id AND status = 'pending'"),
            {"queue_id": str(UUID(queue_id))},
        )
        row = pending_result.mappings().fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="대기 중인 HITL 항목 없음")

        doc_id = str(row["doc_id"])

        await session.execute(
            text("""
                UPDATE hitl_queue
                SET status = 'rejected', reviewer_id = :reviewer_id,
                    review_note = :review_note, reviewed_at = NOW()
                WHERE queue_id = :queue_id
            """),
            {
                "reviewer_id": body.reviewer_id,
                "review_note": body.review_note,
                "queue_id": str(UUID(queue_id)),
            },
        )
        await session.execute(
            text("UPDATE documents SET upload_status = 'rejected' WHERE doc_id = :doc_id"),
            {"doc_id": doc_id},
        )
        await session.commit()

    # 파생 GCS 파일 삭제 (originals/ 제외)
    from app.storage import get_storage
    storage = get_storage()
    deleted = 0
    for prefix in (f"images/{doc_id}/", f"markdown/{doc_id}/"):
        try:
            paths = await storage.list_prefix(prefix)
            for path in paths:
                await storage.delete(path)
                deleted += 1
        except Exception as e:
            logger.warning(f"reject 파일 삭제 실패 (무시): {e}", extra={"doc_id": doc_id})

    logger.info(f"reject 완료 — 파생 파일 {deleted}개 삭제", extra={"doc_id": doc_id})
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
    session_factory = _get_session_factory()

    async with session_factory() as session:
        result = await session.execute(
            text("SELECT * FROM hitl_queue WHERE queue_id = :queue_id"),
            {"queue_id": str(UUID(queue_id))},
        )
        row = result.mappings().fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="HITL 항목 없음")

        await session.execute(
            text("""
                UPDATE hitl_queue
                SET status = 'reprocessing', reviewer_id = :reviewer_id, reviewed_at = NOW()
                WHERE queue_id = :queue_id
            """),
            {"reviewer_id": body.reviewer_id, "queue_id": str(UUID(queue_id))},
        )
        await session.commit()

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

@router.get("/queue/{queue_id}/markdown")
async def get_markdown_endpoint(queue_id: str) -> dict:
    """HITL 항목의 변환된 Markdown 내용 조회."""
    return await _get_hitl_markdown(queue_id)


@router.get("/queue/{queue_id}/page-images")
async def list_page_images(queue_id: str) -> list[dict]:
    """HITL 항목 문서의 파싱 페이지 이미지 목록 반환.

    stage1에서 GCS에 저장된 images/{doc_id}/page_*.png 를 우선 조회하고,
    없으면 chunk_embeddings.metadata.page_image_path 로 폴백한다.
    HITL은 stage5b 이후 stage6(저장) 전에 발생하므로, chunk_embeddings가
    비어있는 상태에서도 stage1에서 저장된 이미지를 제공할 수 있다.
    """
    session_factory = _get_session_factory()
    storage = _storage or get_storage()

    async with session_factory() as session:
        result = await session.execute(
            text("SELECT doc_id::text FROM hitl_queue WHERE queue_id = :queue_id"),
            {"queue_id": str(UUID(queue_id))},
        )
        row = result.mappings().fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="HITL 항목 없음")

    doc_id = row["doc_id"]

    # 1순위: stage1에서 GCS에 저장된 이미지 직접 조회
    paths: list[str] = []
    try:
        raw_paths = await storage.list_prefix(f"images/{doc_id}/")
        # page_N.png 순으로 정렬 (N을 숫자로 파싱)
        def _page_num(p: str) -> int:
            import re
            m = re.search(r"page_(\d+)", p)
            return int(m.group(1)) if m else 0
        paths = sorted(raw_paths, key=_page_num)
    except Exception as e:
        logger.warning(f"storage.list_prefix 실패 — chunk_embeddings 폴백: {e}", extra={"doc_id": doc_id})

    # 2순위: chunk_embeddings.metadata 폴백 (stage6 이후 도달한 경우)
    if not paths:
        async with session_factory() as session:
            result = await session.execute(
                text("""
                    SELECT DISTINCT ce.metadata->>'page_image_path' AS path
                    FROM chunk_embeddings ce
                    JOIN chunks c ON c.chunk_id = ce.chunk_id
                    WHERE c.doc_id::text = :doc_id
                      AND ce.metadata->>'page_image_path' IS NOT NULL
                    ORDER BY path
                """),
                {"doc_id": doc_id},
            )
            paths = [r["path"] for r in result.mappings().fetchall() if r["path"]]

    page_images = []
    for i, path in enumerate(paths, start=1):
        page_images.append({
            "page": i,
            "url": f"/hitl/queue/{queue_id}/page/{i}",
            "gcs_path": path,
        })
    return page_images


@router.get("/queue/{queue_id}/page/{page_num}")
async def get_page_image_bytes(queue_id: str, page_num: int) -> Response:
    """특정 페이지 이미지를 바이트로 반환한다."""
    storage = _storage or get_storage()
    session_factory = _get_session_factory()

    async with session_factory() as session:
        result = await session.execute(
            text("SELECT doc_id::text FROM hitl_queue WHERE queue_id = :queue_id"),
            {"queue_id": str(UUID(queue_id))},
        )
        row = result.mappings().fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="HITL 항목 없음")

    doc_id = row["doc_id"]

    # 1순위: stage1 GCS 저장 이미지 직접 조회
    paths: list[str] = []
    try:
        import re
        raw_paths = await storage.list_prefix(f"images/{doc_id}/")
        def _page_num_key(p: str) -> int:
            m = re.search(r"page_(\d+)", p)
            return int(m.group(1)) if m else 0
        paths = sorted(raw_paths, key=_page_num_key)
    except Exception:
        pass

    # 2순위: chunk_embeddings 폴백
    if not paths:
        async with session_factory() as session:
            result = await session.execute(
                text("""
                    SELECT DISTINCT ce.metadata->>'page_image_path' AS path
                    FROM chunk_embeddings ce
                    JOIN chunks c ON c.chunk_id = ce.chunk_id
                    WHERE c.doc_id::text = :doc_id
                      AND ce.metadata->>'page_image_path' IS NOT NULL
                    ORDER BY path
                """),
                {"doc_id": doc_id},
            )
            paths = [r["path"] for r in result.mappings().fetchall() if r["path"]]

    if page_num < 1 or page_num > len(paths):
        raise HTTPException(status_code=404, detail=f"페이지 {page_num} 없음 (총 {len(paths)}페이지)")

    gcs_path = paths[page_num - 1]
    try:
        img_bytes = await storage.load(gcs_path)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"이미지 로드 실패: {exc}") from exc

    media_type = "image/png"
    if gcs_path.lower().endswith((".jpg", ".jpeg")):
        media_type = "image/jpeg"
    return Response(content=img_bytes, media_type=media_type)


@router.get("/queue/{queue_id}/suggest-category")
async def suggest_category_endpoint(queue_id: str) -> dict:
    """KB Evolution — AI 카테고리 제안 조회."""
    return await _suggest_category_for_hitl(queue_id)


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
        _apply_category_from_hitl,
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
    issues = d.get("issues")
    if isinstance(issues, str):
        try:
            issues = json.loads(issues)
        except (json.JSONDecodeError, TypeError):
            issues = None
    d["issues"] = issues
    return HitlQueueItem(**d)


async def _get_hitl_markdown(queue_id: str) -> dict:
    """HITL 항목의 변환된 Markdown 내용을 반환한다."""
    storage = _storage or get_storage()
    session_factory = _get_session_factory()

    async with session_factory() as session:
        result = await session.execute(
            text("""
                SELECT hq.issues, hq.doc_id::text, d.markdown_path AS doc_markdown_path
                FROM hitl_queue hq
                LEFT JOIN documents d USING (doc_id)
                WHERE hq.queue_id = :queue_id
            """),
            {"queue_id": str(UUID(queue_id))},
        )
        row = result.mappings().fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="HITL 항목 없음")

    raw_issues = row["issues"] or {}
    issues = json.loads(raw_issues) if isinstance(raw_issues, str) else raw_issues
    doc_id = row["doc_id"]

    # 우선순위: issues.markdown_storage_path → documents.markdown_path → 표준 경로 폴백
    markdown_path = (
        (issues.get("markdown_storage_path") if isinstance(issues, dict) else None)
        or row.get("doc_markdown_path")
        or f"markdown/{doc_id}/raw.md"
    )

    try:
        raw = await storage.load(markdown_path)
        markdown = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Markdown 로드 실패: {exc}") from exc

    return {"markdown": markdown, "path": markdown_path}


async def _suggest_category_for_hitl(queue_id: str) -> dict:
    """hitl_queue.issues에 저장된 category_reasoning / category_alternatives를 반환한다."""
    session_factory = _get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            text("SELECT issues FROM hitl_queue WHERE queue_id = :queue_id"),
            {"queue_id": str(UUID(queue_id))},
        )
        row = result.mappings().fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="HITL 항목 없음")

    raw_issues = row["issues"] or {}
    issues_data = json.loads(raw_issues) if isinstance(raw_issues, str) else raw_issues

    reasoning = issues_data.get("category_reasoning", "")
    alternatives = issues_data.get("category_alternatives", [])
    proposed = _extract_proposed_category(issues_data.get("issues", []))

    suggested = ([proposed] if proposed else []) + [
        a for a in alternatives if a != proposed
    ]

    return {
        "suggested": suggested[:3],
        "reasoning": reasoning,
        "category_reasoning": reasoning,
        "alternatives": alternatives,
        "category_alternatives": alternatives,
    }


def _extract_proposed_category(issues: list[str]) -> str:
    """issues 목록에서 '새 카테고리 제안: ...' 패턴으로 카테고리명을 추출한다."""
    for issue in issues:
        if "새 카테고리 제안:" in issue:
            return issue.split("새 카테고리 제안:")[-1].strip().strip("'\"")
    return ""


async def _apply_category_from_hitl(
    queue_id: str,
    category: str,
    description: str = "",
) -> None:
    """선택된 카테고리를 DB에 추가하고 파이프라인 재처리를 시작한다."""
    from app.categories_db import add_category

    session_factory = _get_session_factory()

    # 1. categories 테이블에 추가 (이미 있으면 무시)
    await add_category(session_factory, category, description)

    # 2. HITL 항목 조회 + 상태 업데이트
    async with session_factory() as session:
        result = await session.execute(
            text("SELECT * FROM hitl_queue WHERE queue_id = :queue_id"),
            {"queue_id": str(UUID(queue_id))},
        )
        row = result.mappings().fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="HITL 항목 없음")

        await session.execute(
            text("""
                UPDATE hitl_queue
                SET status = 'approved', reviewed_at = NOW()
                WHERE queue_id = :queue_id
            """),
            {"queue_id": str(UUID(queue_id))},
        )
        await session.commit()

    # 3. 파이프라인 재처리 (사람이 승인한 카테고리 적용)
    raw_issues = row["issues"] or {}
    issues = json.loads(raw_issues) if isinstance(raw_issues, str) else raw_issues

    await _reprocess_document(
        doc_id=str(row["doc_id"]),
        stage=row["stage"],
        issues=issues,
        corrected_category=category,
        skip_validation=True,
    )


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
    """
    session_factory = _db_session_factory
    if session_factory is None:
        logger.error("DB session factory 미초기화 — 재처리 중단", extra={"doc_id": doc_id})
        return
    storage = _storage or get_storage()

    # 재처리 시작 상태 업데이트
    async with session_factory() as session:
        await session.execute(
            text("UPDATE documents SET upload_status = 'reprocessing' WHERE doc_id = :doc_id"),
            {"doc_id": doc_id},
        )
        await session.commit()

    # 저장된 Markdown 경로 조회
    markdown_path = issues.get("markdown_storage_path") if isinstance(issues, dict) else None

    if markdown_path is None:
        try:
            async with session_factory() as session:
                result = await session.execute(
                    text("SELECT markdown_path FROM documents WHERE doc_id = :doc_id"),
                    {"doc_id": doc_id},
                )
                doc_row = result.mappings().fetchone()
                if doc_row and doc_row["markdown_path"]:
                    markdown_path = doc_row["markdown_path"]
        except Exception as e:
            logger.warning(f"documents.markdown_path 조회 실패: {e}", extra={"doc_id": doc_id})

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
            logger.error(f"Markdown 로드 실패 — 재처리 중단: {e}", extra={"doc_id": doc_id})
            await _mark_reprocess_failed(session_factory, doc_id)
            return

    if raw_markdown is None:
        logger.error("재처리할 Markdown이 없음 — 재처리 중단", extra={"doc_id": doc_id})
        await _mark_reprocess_failed(session_factory, doc_id)
        return

    from app.pipeline.models import make_reprocess_state
    from app.pipeline.stage2_validate_agent import stage2_validate
    from app.pipeline.stage3_chunk import stage3_chunk
    from app.pipeline.stage4_chunk_validate import stage4_chunk_validate
    from app.pipeline.stage5_metadata_agent import stage5_metadata
    from app.pipeline.stage5b_metadata_validate_agent import stage5b_metadata_validate
    from app.pipeline.stage6_store import stage6_store

    start_validated = skip_validation or (corrected_markdown is None)

    state = make_reprocess_state(
        doc_id=doc_id,
        raw_markdown=raw_markdown,
        markdown_path=markdown_path,
        start_validated=start_validated,
    )

    if corrected_category:
        if state.get("metadata") is None:
            state["metadata"] = {}
        state["metadata"]["category"] = corrected_category
        state["category_is_new"] = False
        state["category_reasoning"] = ""
        state["category_alternatives"] = []

    _doc_uuid = UUID(doc_id)
    _stage6_timeout = int(os.getenv("STAGE6_TIMEOUT_SECONDS", "900"))

    def _harness(
        pipeline_stage: DocPipelineStage,
        agent_name: str,
        timeout: int | None = None,
    ) -> AgentHarness:
        return AgentHarness(
            trace_id=new_pipeline_trace(pipeline_stage, doc_id=_doc_uuid),
            agent_name=agent_name,
            db_session_factory=session_factory,
            doc_id=_doc_uuid,
            timeout=timeout,
        )

    try:
        # Stage 2: 검증 (corrected_markdown 제공 시만)
        if not start_validated:
            try:
                async with _harness(DocPipelineStage.MARKDOWN_VALIDATE, "MarkdownValidateAgent") as h:
                    result = await h.run(stage2_validate, state)
            except Exception:
                raise
            state = {**state, **result}
            if state.get("hitl_required"):
                await _abort_reprocess_with_hitl(
                    session_factory, doc_id, "stage2_validate",
                    state.get("quality_issues") or [],
                )
                return
            if state.get("status") == "failed":
                await _mark_reprocess_failed(session_factory, doc_id)
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
                session_factory, doc_id, "stage4_chunk_validate",
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
                session_factory, doc_id, "stage5b_metadata_validate",
                state.get("metadata_issues") or [],
            )
            return

        # Stage 6: 저장 (대용량 문서 대응 전용 타임아웃)
        async with _harness(
            DocPipelineStage.STORE_ROUTE, "StoreRouteAgent", timeout=_stage6_timeout
        ) as h:
            result = await h.run(
                stage6_store,
                state,
                db_session_factory=session_factory,
                storage=storage,
            )
        state = {**state, **result}

        logger.info(
            "재처리 완료",
            extra={"doc_id": doc_id, "status": state.get("status")},
        )

    except Exception as e:
        logger.error(f"재처리 중 예외 발생: {e}", extra={"doc_id": doc_id})
        await _mark_reprocess_failed(session_factory, doc_id)


async def _mark_reprocess_failed(
    session_factory: async_sessionmaker[AsyncSession],
    doc_id: str,
) -> None:
    """재처리 실패 시 문서 상태 업데이트."""
    try:
        async with session_factory() as session:
            await session.execute(
                text("UPDATE documents SET upload_status = 'reprocess_failed' WHERE doc_id = :doc_id"),
                {"doc_id": doc_id},
            )
            await session.commit()
    except Exception as e:
        logger.warning(f"재처리 실패 상태 업데이트 오류: {e}")


async def _enqueue_hitl_reprocess(
    session_factory: async_sessionmaker[AsyncSession],
    doc_id: str,
    stage: str,
    issues: list[str],
) -> None:
    """재처리 중 HITL 재트리거 시 hitl_queue에 새 항목을 삽입한다."""
    reason = ", ".join(issues) if issues else "재처리 중 검증 실패"
    try:
        async with session_factory() as session:
            await session.execute(
                text("""
                    INSERT INTO hitl_queue (doc_id, stage, reason, issues, status)
                    VALUES (:doc_id, :stage, :reason, CAST(:issues AS jsonb), 'pending')
                """),
                {
                    "doc_id": doc_id,
                    "stage": stage,
                    "reason": reason,
                    "issues": json.dumps({"issues": issues}),
                },
            )
            await session.commit()
        logger.info("재처리 HITL 재등록", extra={"doc_id": doc_id, "stage": stage})
    except Exception as e:
        logger.error(f"재처리 HITL hitl_queue INSERT 실패: {e}", extra={"doc_id": doc_id})


async def _abort_reprocess_with_hitl(
    session_factory: async_sessionmaker[AsyncSession],
    doc_id: str,
    stage_name: str,
    issues: list[str],
) -> None:
    """재처리 중 HITL 재트리거 시 큐 등록 + 문서 상태를 hitl_pending으로 설정한다."""
    logger.warning(f"재처리 {stage_name} HITL 재트리거", extra={"doc_id": doc_id})
    await _enqueue_hitl_reprocess(session_factory, doc_id, stage_name, issues)
    try:
        async with session_factory() as session:
            await session.execute(
                text("UPDATE documents SET upload_status = 'hitl_pending' WHERE doc_id = :doc_id"),
                {"doc_id": doc_id},
            )
            await session.commit()
    except Exception as e:
        logger.warning(f"hitl_pending 상태 업데이트 오류: {e}")
