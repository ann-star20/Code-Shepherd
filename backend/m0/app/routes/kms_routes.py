"""
KMS FastAPI 라우터 — SQLAlchemy async 버전

엔드포인트:
    POST /kms/upload                    문서 업로드 → 파이프라인 실행
    GET  /kms/status/{doc_id}           처리 상태 조회
    GET  /kms/docs                      문서 목록 조회 (status 필터, 페이지네이션)
    GET  /kms/docs/{doc_id}/markdown    파싱된 Markdown 반환
    GET  /kms/docs/{doc_id}/metadata    Stage 5 추출 메타데이터 조회
    GET  /kms/docs/{doc_id}/details     에이전트 트레이스 + 청크 상세
    GET  /kms/search                    pgVector 코사인 유사도 검색
    GET  /kms/stats                     전체 성공률 + 스테이지별 평균 처리시간
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile

from app.dependencies import get_current_kms_user
from app.pipeline.graph_sync import sync_old_document_version
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.pipeline.models import DocPipelineState

_OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "bge-m3")

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/kms", tags=["KMS"])

SUPPORTED_EXTENSIONS = {"pdf", "docx", "pptx", "txt", "md"}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB

ALLOWED_DOC_STATUSES = {
    "processing", "stored", "stored_partial", "failed",
    "hitl_pending", "approved", "rejected", "reprocess_failed", "reprocessing",
}


# ---------------------------------------------------------------------------
# 응답 모델
# ---------------------------------------------------------------------------

class UploadResponse(BaseModel):
    doc_id: str
    status: str
    message: str
    quality_score: float | None = None
    hitl_required: bool = False
    chunk_count: int | None = None


class AgentTraceItem(BaseModel):
    trace_id: str
    agent_name: str
    status: str
    started_at: str | None = None
    ended_at: str | None = None
    execution_ms: int | None = None
    error_message: str | None = None


class StatusResponse(BaseModel):
    doc_id: str
    status: str
    current_stage: str | None = None
    error: str | None = None
    agent_traces: list[AgentTraceItem] = []


class SearchResultItem(BaseModel):
    chunk_id: str
    content: str
    score: float
    metadata: dict | None = None
    doc_title: str | None = None
    page_image_path: str | None = None


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultItem]
    total: int


class ChunkItem(BaseModel):
    chunk_id: str
    chunk_type: str
    content: str
    token_count: int | None = None
    section_header: str | None = None
    page_number: int | None = None
    chunk_index: int | None = None


class DocDetailsResponse(BaseModel):
    doc_id: str
    title: str | None = None
    file_type: str | None = None
    status: str
    created_at: str | None = None
    parser_used: str | None = None
    quality_score: float | None = None
    doc_complexity: str | None = None
    parsing_time_ms: int | None = None
    agent_traces: list[AgentTraceItem]
    chunks: list[ChunkItem]


class DocListItem(BaseModel):
    doc_id: str
    title: str | None = None
    file_type: str | None = None
    status: str
    created_at: str | None = None
    neo4j_synced: bool | None = None
    category: str | None = None
    doc_complexity: str | None = None


class DocListResponse(BaseModel):
    docs: list[DocListItem]
    total: int
    limit: int
    offset: int


class MarkdownResponse(BaseModel):
    doc_id: str
    markdown_path: str
    content: str


class DocMetadataResponse(BaseModel):
    doc_id: str
    title: str | None = None
    category: str | None = None
    source: str | None = None
    file_type: str | None = None
    created_at: str | None = None
    team: str | None = None
    tags: list[str] = []


class StageStatItem(BaseModel):
    agent_name: str
    avg_execution_ms: float
    run_count: int


class KmsStatsResponse(BaseModel):
    total_runs: int
    success_count: int
    fail_count: int
    success_rate: float
    stage_stats: list[StageStatItem]


class EntityItem(BaseModel):
    name: str
    type: str | None = None
    description: str | None = None


class DocEntitiesResponse(BaseModel):
    doc_id: str
    entities: list[EntityItem]
    total: int


class DocStatsResponse(BaseModel):
    doc_id: str
    rag_reference_count: int
    last_used_at: str | None = None
    recent_search_reflected: bool


class RelatedDocItem(BaseModel):
    doc_id: str
    title: str | None = None
    category: str | None = None
    shared_count: int


class DocRelatedResponse(BaseModel):
    doc_id: str
    related: list[RelatedDocItem]
    total: int


# ---------------------------------------------------------------------------
# 중복 감지 응답 모델
# ---------------------------------------------------------------------------

class DuplicateExistingDoc(BaseModel):
    doc_id: str
    original_filename: str | None = None
    upload_status: str | None = None
    created_at: str | None = None


class CheckDuplicateResponse(BaseModel):
    status: str  # "identical" | "modified" | "new"
    existing_doc: DuplicateExistingDoc | None = None


class ReplaceDocumentResponse(BaseModel):
    new_doc_id: str
    old_doc_id: str
    status: str
    message: str


class DeleteDocumentResponse(BaseModel):
    doc_id: str
    status: str
    sync_warning: str | None = None


# ---------------------------------------------------------------------------
# 의존성 — main.py lifespan에서 주입
# ---------------------------------------------------------------------------

_db_session_factory: async_sessionmaker[AsyncSession] | None = None
_pipeline = None   # LangGraph compiled graph
_storage = None    # Storage 구현체


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _db_session_factory is None:
        raise RuntimeError("DB session factory가 초기화되지 않았습니다. lifespan을 확인하세요.")
    return _db_session_factory


def _get_pipeline():
    if _pipeline is None:
        raise RuntimeError("파이프라인이 초기화되지 않았습니다. lifespan을 확인하세요.")
    return _pipeline


def _get_storage():
    if _storage is None:
        raise RuntimeError("Storage가 초기화되지 않았습니다. lifespan을 확인하세요.")
    return _storage


# ---------------------------------------------------------------------------
# 엔드포인트
# ---------------------------------------------------------------------------

@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    source: str = Form(default="upload"),
    permission_level: str = Form(default="public"),
    visibility: str = Form(default="all"),
    file_hash: str | None = Form(default=None),
    current_user: dict = Depends(get_current_kms_user),
) -> UploadResponse:
    """
    문서를 업로드하고 KMS 파이프라인을 실행한다.

    지원 형식: PDF · DOCX · PPTX · TXT · MD
    """
    filename = file.filename or "unknown"
    ext = Path(filename).suffix.lstrip(".").lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"지원하지 않는 파일 형식: .{ext}. 지원 형식: {SUPPORTED_EXTENSIONS}",
        )

    if file.size is not None and file.size > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"파일 크기 초과: {file.size // (1024 * 1024)}MB. 최대 {MAX_UPLOAD_BYTES // (1024 * 1024)}MB",
        )

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"파일 크기 초과: {len(content) // (1024 * 1024)}MB. 최대 {MAX_UPLOAD_BYTES // (1024 * 1024)}MB",
        )

    doc_id = str(uuid4())
    session_factory = _get_session_factory()
    _get_pipeline()

    # hitl_queue가 documents(doc_id)를 FK로 참조하므로 파이프라인 전 초기 레코드 삽입
    try:
        async with session_factory() as session:
            await session.execute(
                text("""
                    INSERT INTO documents
                        (doc_id, title, source, file_type, original_filename, upload_status, created_at)
                    VALUES
                        (:doc_id, :title, :source, :file_type, :original_filename, 'processing', NOW())
                    ON CONFLICT (doc_id) DO NOTHING
                """),
                {
                    "doc_id": doc_id,
                    "title": filename,
                    "source": source,
                    "file_type": ext,
                    "original_filename": filename,
                },
            )
            await session.commit()
    except (ConnectionRefusedError, OSError) as e:
        logger.error(f"DB 연결 실패: {e}")
        raise HTTPException(
            status_code=503,
            detail="DB 연결 실패 — 잠시 후 다시 시도하세요.",
        )

    with tempfile.NamedTemporaryFile(
        delete=False, suffix=f".{ext}", prefix=f"kms_{doc_id}_"
    ) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    initial_state = _build_initial_state(
        doc_id, source, tmp_path, ext, filename,
        department_id=current_user["team"],
        user_id=current_user["user_id"],
        permission_level=permission_level,
        visibility=visibility,
        file_hash=file_hash,
    )
    background_tasks.add_task(_run_pipeline_background, initial_state)

    return UploadResponse(
        doc_id=doc_id,
        status="processing",
        message="Document upload accepted. Check /kms/status/{doc_id} for progress.",
        hitl_required=False,
        chunk_count=0,
    )


def _build_initial_state(
    doc_id: str,
    source: str,
    tmp_path: str,
    ext: str,
    filename: str,
    department_id: str | None = None,
    user_id: str | None = None,
    permission_level: str = "public",
    visibility: str = "all",
    file_hash: str | None = None,
) -> DocPipelineState:
    return {
        "doc_id": doc_id,
        "source": source,
        "file_path": tmp_path,
        "file_type": ext,
        "original_filename": filename,
        "raw_markdown": None,
        "markdown_storage_path": None,
        "parser_used": None,
        "parser_quality_score": None,
        "doc_complexity": None,
        "has_tables": None,
        "has_images": None,
        "page_count": None,
        "parsing_time_ms": None,
        "parser_warnings": None,
        "fallback_used": None,
        "image_refs": None,
        "image_data": None,
        "validated_markdown": None,
        "quality_score": None,
        "quality_issues": None,
        "hitl_required": False,
        "chunks": None,
        "chunk_validation_passed": False,
        "chunk_validation_issues": None,
        "metadata": None,
        "neo4j_entities": None,
        "neo4j_relations": None,
        "metadata_valid": None,
        "metadata_score": None,
        "metadata_issues": None,
        "stored": False,
        "neo4j_stored": None,
        "storage_paths": None,
        "status": "processing",
        "error": None,
        "current_stage": "init",
        "department_id": department_id,
        "user_id": user_id,
        "permission_level": permission_level,
        "visibility": visibility,
        "file_hash": file_hash,
    }


async def _run_pipeline_background(initial_state: DocPipelineState) -> None:
    doc_id = initial_state["doc_id"]
    tmp_path = initial_state["file_path"]
    try:
        result: DocPipelineState = await _get_pipeline().ainvoke(initial_state)
        final_status = result.get("status", "failed")
        await _update_document_status(doc_id, final_status, result)
    except Exception as e:
        logger.error(f"파이프라인 실행 실패: {e}", extra={"doc_id": doc_id})
        await _update_document_status(doc_id, "failed", error_message=str(e))
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            logger.warning("임시 파일 정리 실패", extra={"doc_id": doc_id, "path": tmp_path})


async def _update_document_status(
    doc_id: str,
    status: str,
    state: dict | None = None,
    error_message: str | None = None,
) -> None:
    session_factory = _get_session_factory()
    async with session_factory() as session:
        if state and any(state.get(k) for k in ("parser_used", "doc_complexity", "parsing_time_ms", "quality_score")):
            await session.execute(
                text("""
                    UPDATE documents
                    SET upload_status   = :status,
                        parser_used     = COALESCE(:parser_used, parser_used),
                        doc_complexity  = COALESCE(:doc_complexity, doc_complexity),
                        parsing_time_ms = COALESCE(:parsing_time_ms, parsing_time_ms),
                        quality_score   = COALESCE(:quality_score, quality_score),
                        error_message   = COALESCE(:error_message, error_message)
                    WHERE doc_id = :doc_id
                """),
                {
                    "status": status,
                    "parser_used": state.get("parser_used"),
                    "doc_complexity": state.get("doc_complexity"),
                    "parsing_time_ms": state.get("parsing_time_ms"),
                    "quality_score": state.get("quality_score"),
                    "error_message": error_message,
                    "doc_id": doc_id,
                },
            )
        else:
            await session.execute(
                text("""
                    UPDATE documents
                    SET upload_status = :status,
                        error_message = COALESCE(:error_message, error_message)
                    WHERE doc_id = :doc_id
                """),
                {"status": status, "error_message": error_message, "doc_id": doc_id},
            )
        await session.commit()


@router.get("/status/{doc_id}", response_model=StatusResponse)
async def get_document_status(
    doc_id: str,
    current_user: dict = Depends(get_current_kms_user),
) -> StatusResponse:
    """문서 처리 상태를 조회한다. agent_traces를 포함해 파이프라인 진행 상황을 실시간 반환."""
    try:
        UUID(doc_id)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"유효하지 않은 doc_id 형식: {doc_id}")

    session_factory = _get_session_factory()
    async with session_factory() as session:
        doc_result = await session.execute(
            text("SELECT upload_status, error_message FROM documents WHERE doc_id = :doc_id"),
            {"doc_id": doc_id},
        )
        row = doc_result.mappings().fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"문서를 찾을 수 없음: {doc_id}")

        trace_result = await session.execute(
            text("""
                SELECT trace_id, agent_name, status,
                       started_at::text, ended_at::text,
                       execution_ms, error_message
                FROM agent_traces
                WHERE doc_id = :doc_id
                ORDER BY started_at ASC NULLS LAST
            """),
            {"doc_id": doc_id},
        )
        trace_rows = trace_result.mappings().fetchall()

    traces = [
        AgentTraceItem(
            trace_id=r["trace_id"],
            agent_name=r["agent_name"],
            status=r["status"],
            started_at=r["started_at"],
            ended_at=r["ended_at"],
            execution_ms=r["execution_ms"],
            error_message=r["error_message"],
        )
        for r in trace_rows
    ]

    upload_status = row["upload_status"]
    # documents.error_message 우선, 없으면 agent_traces에서 역추적
    error_msg: str | None = row["error_message"] if row["error_message"] else None
    if upload_status == "failed" and not error_msg:
        fail_row = next(
            (r for r in trace_rows if r["status"] == "fail" and r["error_message"]), None
        )
        if fail_row:
            error_msg = fail_row["error_message"]
        else:
            running_row = next((r for r in trace_rows if r["status"] == "running"), None)
            if running_row:
                error_msg = f"{running_row['agent_name']} 처리 중 오류 발생 (서버 로그 확인 필요)"

    return StatusResponse(
        doc_id=doc_id,
        status=upload_status,
        current_stage=None,
        error=error_msg,
        agent_traces=traces,
    )


@router.get("/search", response_model=SearchResponse)
async def search_kms(
    q: str = Query(..., min_length=1, description="검색 쿼리"),
    limit: int = Query(default=5, ge=1, le=20, description="반환할 최대 청크 수"),
    category: str | None = Query(default=None, description="카테고리 필터 (metadata.category)"),
    current_user: dict = Depends(get_current_kms_user),
) -> SearchResponse:
    """
    pgVector 코사인 유사도 검색.
    쿼리를 Ollama bge-m3로 임베딩한 뒤 가장 유사한 child chunk를 반환한다.
    """
    try:
        query_embedding = await _embed_query(q)
    except Exception as e:
        logger.error(f"쿼리 임베딩 실패: {e}")
        raise HTTPException(status_code=503, detail=f"임베딩 서비스 오류: {e}")

    embedding_str = f"[{','.join(str(v) for v in query_embedding)}]"

    session_factory = _get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            text("""
                SELECT
                    ce.chunk_id::text,
                    ce.content,
                    1 - (ce.embedding <=> CAST(:embedding AS vector)) AS score,
                    ce.metadata,
                    d.title AS doc_title
                FROM chunk_embeddings ce
                LEFT JOIN chunks c ON ce.chunk_id = c.chunk_id
                LEFT JOIN documents d ON c.doc_id = d.doc_id
                WHERE d.upload_status IN ('stored', 'stored_partial')
                AND (:category IS NULL OR ce.metadata->>'category' = :category)
                AND (
                    d.permission_level = 'public'
                    OR d.department_id = :user_team
                    OR d.user_id = :user_id
                )
                ORDER BY ce.embedding <=> CAST(:embedding AS vector)
                LIMIT :limit
            """),
            {
                "embedding": embedding_str,
                "limit": limit,
                "category": category,
                "user_team": current_user["team"],
                "user_id": current_user["user_id"],
            },
        )
        rows = result.mappings().fetchall()

    if not rows:
        logger.info(f"KMS 검색 결과 없음: query='{q[:50]}'")

    results = [
        SearchResultItem(
            chunk_id=row["chunk_id"],
            content=row["content"],
            score=float(row["score"]),
            metadata=row["metadata"] if isinstance(row["metadata"], dict) else None,
            doc_title=row["doc_title"],
            page_image_path=(row["metadata"] if isinstance(row["metadata"], dict) else {}).get("page_image_path"),
        )
        for row in rows
    ]

    return SearchResponse(query=q, results=results, total=len(results))


@router.get("/docs", response_model=DocListResponse)
async def list_documents(
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
    current_user: dict = Depends(get_current_kms_user),
) -> DocListResponse:
    """문서 목록을 조회한다. status 필터와 페이지네이션을 지원한다."""
    if limit <= 0 or limit > 10000:
        raise HTTPException(status_code=422, detail=f"limit은 1~10000 사이여야 합니다: {limit}")
    if offset < 0:
        raise HTTPException(status_code=422, detail=f"offset은 0 이상이어야 합니다: {offset}")
    if status is not None and status not in ALLOWED_DOC_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"허용되지 않는 status 값: '{status}'. 허용값: {sorted(ALLOWED_DOC_STATUSES)}",
        )

    session_factory = _get_session_factory()
    async with session_factory() as session:
        perm_params = {
            "user_team": current_user["team"],
            "user_id": current_user["user_id"],
        }
        _perm_clause = """
            AND (
                permission_level = 'public'
                OR department_id = :user_team
                OR user_id = :user_id
            )
        """
        if status is not None:
            count_result = await session.execute(
                text(
                    "SELECT COUNT(*) AS count FROM documents "
                    "WHERE upload_status = :status" + _perm_clause
                ),
                {"status": status, **perm_params},
            )
        else:
            count_result = await session.execute(
                text("SELECT COUNT(*) AS count FROM documents WHERE TRUE" + _perm_clause),
                perm_params,
            )
        count_row = count_result.mappings().fetchone()

        if status is not None:
            list_result = await session.execute(
                text("""
                    SELECT doc_id::text, title, file_type, upload_status, created_at,
                           neo4j_synced, category, doc_complexity
                    FROM documents
                    WHERE upload_status = :status
                """ + _perm_clause + """
                    ORDER BY created_at DESC NULLS LAST
                    LIMIT :limit OFFSET :offset
                """),
                {"status": status, "limit": limit, "offset": offset, **perm_params},
            )
        else:
            list_result = await session.execute(
                text("""
                    SELECT doc_id::text, title, file_type, upload_status, created_at,
                           neo4j_synced, category, doc_complexity
                    FROM documents
                    WHERE TRUE
                """ + _perm_clause + """
                    ORDER BY created_at DESC NULLS LAST
                    LIMIT :limit OFFSET :offset
                """),
                {"limit": limit, "offset": offset, **perm_params},
            )
        rows = list_result.mappings().fetchall()

    total = count_row["count"] if count_row else 0

    docs = [
        DocListItem(
            doc_id=r["doc_id"],
            title=r["title"],
            file_type=r["file_type"],
            status=r["upload_status"],
            created_at=r["created_at"].isoformat() if r["created_at"] else None,
            neo4j_synced=r["neo4j_synced"],
            category=r["category"],
            doc_complexity=r["doc_complexity"],
        )
        for r in rows
    ]

    return DocListResponse(docs=docs, total=total, limit=limit, offset=offset)


@router.get("/docs/{doc_id}/markdown", response_model=MarkdownResponse)
async def get_doc_markdown(
    doc_id: str,
    current_user: dict = Depends(get_current_kms_user),
) -> MarkdownResponse:
    """문서의 파싱된 Markdown 원문을 Storage에서 반환한다."""
    storage = _get_storage()

    try:
        UUID(doc_id)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"유효하지 않은 doc_id 형식: {doc_id}")

    session_factory = _get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            text("SELECT markdown_path FROM documents WHERE doc_id = :doc_id"),
            {"doc_id": doc_id},
        )
        row = result.mappings().fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail=f"문서를 찾을 수 없음: {doc_id}")

    markdown_path: str | None = row["markdown_path"]
    if not markdown_path:
        raise HTTPException(
            status_code=404,
            detail=f"문서의 Markdown이 아직 생성되지 않았습니다: {doc_id}",
        )

    try:
        content_bytes = await storage.load(markdown_path)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"Storage에 Markdown 파일 없음: {markdown_path}"
        )
    except Exception as e:
        logger.error(f"Storage 로드 실패: {e}", extra={"doc_id": doc_id, "path": markdown_path})
        raise HTTPException(status_code=503, detail=f"Storage 오류: {e}")

    return MarkdownResponse(
        doc_id=doc_id,
        markdown_path=markdown_path,
        content=content_bytes.decode("utf-8", errors="replace"),
    )


@router.get("/docs/{doc_id}/metadata", response_model=DocMetadataResponse)
async def get_doc_metadata(
    doc_id: str,
    current_user: dict = Depends(get_current_kms_user),
) -> DocMetadataResponse:
    """Stage 5에서 추출된 문서 메타데이터를 반환한다."""
    try:
        UUID(doc_id)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"유효하지 않은 doc_id 형식: {doc_id}")

    session_factory = _get_session_factory()
    async with session_factory() as session:
        doc_result = await session.execute(
            text("""
                SELECT title, category, source, file_type, created_at
                FROM documents WHERE doc_id = :doc_id
            """),
            {"doc_id": doc_id},
        )
        doc_row = doc_result.mappings().fetchone()
        if doc_row is None:
            raise HTTPException(status_code=404, detail=f"문서를 찾을 수 없음: {doc_id}")

        meta_result = await session.execute(
            text("""
                SELECT ce.metadata
                FROM chunk_embeddings ce
                INNER JOIN chunks c ON ce.chunk_id = c.chunk_id
                WHERE c.doc_id = :doc_id
                LIMIT 1
            """),
            {"doc_id": doc_id},
        )
        meta_row = meta_result.mappings().fetchone()

    team: str | None = None
    tags: list[str] = []
    if meta_row and meta_row["metadata"]:
        meta = meta_row["metadata"] if isinstance(meta_row["metadata"], dict) else {}
        team = meta.get("team")
        tags = meta.get("tags") or []

    return DocMetadataResponse(
        doc_id=doc_id,
        title=doc_row["title"],
        category=doc_row["category"],
        source=doc_row["source"],
        file_type=doc_row["file_type"],
        created_at=doc_row["created_at"].isoformat() if doc_row["created_at"] else None,
        team=team,
        tags=tags,
    )


@router.get("/docs/{doc_id}/details", response_model=DocDetailsResponse)
async def get_doc_details(
    doc_id: str,
    current_user: dict = Depends(get_current_kms_user),
) -> DocDetailsResponse:
    """에이전트 트레이스 + 청크 상세 조회."""
    try:
        UUID(doc_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="유효하지 않은 doc_id 형식")

    session_factory = _get_session_factory()
    async with session_factory() as session:
        doc_result = await session.execute(
            text("""
                SELECT title, file_type, upload_status, created_at,
                       parser_used, quality_score, doc_complexity, parsing_time_ms,
                       permission_level, department_id, user_id
                FROM documents WHERE doc_id = :doc_id
            """),
            {"doc_id": doc_id},
        )
        doc_row = doc_result.mappings().fetchone()
        if doc_row is None:
            raise HTTPException(status_code=404, detail=f"문서를 찾을 수 없음: {doc_id}")

        perm = doc_row["permission_level"]
        owner_user = doc_row["user_id"]
        owner_dept = doc_row["department_id"]
        can_access = (
            perm == "public"
            or (owner_dept is not None and owner_dept == current_user["team"])
            or owner_user == current_user["user_id"]
        )
        if not can_access:
            raise HTTPException(status_code=403, detail="이 문서에 접근할 권한이 없습니다.")

        trace_result = await session.execute(
            text("""
                SELECT trace_id::text, agent_name, status,
                       started_at, ended_at, execution_ms, error_message
                FROM agent_traces
                WHERE doc_id = :doc_id
                ORDER BY started_at NULLS LAST
            """),
            {"doc_id": doc_id},
        )
        trace_rows = trace_result.mappings().fetchall()

        chunk_result = await session.execute(
            text("""
                SELECT chunk_id::text, chunk_type, content, token_count,
                       section_header, page_number, chunk_index
                FROM chunks
                WHERE doc_id = :doc_id
                ORDER BY
                    CASE WHEN chunk_type = 'parent' THEN 0 ELSE 1 END,
                    chunk_index NULLS LAST,
                    page_number NULLS LAST
            """),
            {"doc_id": doc_id},
        )
        chunk_rows = chunk_result.mappings().fetchall()

    traces = [
        AgentTraceItem(
            trace_id=r["trace_id"],
            agent_name=r["agent_name"],
            status=r["status"],
            started_at=r["started_at"].isoformat() if r["started_at"] else None,
            ended_at=r["ended_at"].isoformat() if r["ended_at"] else None,
            execution_ms=r["execution_ms"],
            error_message=r["error_message"],
        )
        for r in trace_rows
    ]

    chunks = [
        ChunkItem(
            chunk_id=r["chunk_id"],
            chunk_type=r["chunk_type"],
            content=r["content"],
            token_count=r["token_count"],
            section_header=r["section_header"],
            page_number=r["page_number"],
            chunk_index=r["chunk_index"],
        )
        for r in chunk_rows
    ]

    return DocDetailsResponse(
        doc_id=doc_id,
        title=doc_row["title"],
        file_type=doc_row["file_type"],
        status=doc_row["upload_status"],
        created_at=doc_row["created_at"].isoformat() if doc_row["created_at"] else None,
        parser_used=doc_row["parser_used"],
        quality_score=doc_row["quality_score"],
        doc_complexity=doc_row["doc_complexity"],
        parsing_time_ms=doc_row["parsing_time_ms"],
        agent_traces=traces,
        chunks=chunks,
    )


@router.delete("/docs/{doc_id}", response_model=DeleteDocumentResponse)
async def delete_document(
    doc_id: str,
    current_user: dict = Depends(get_current_kms_user),
) -> DeleteDocumentResponse:
    """문서를 4개 저장소(PG/pgvector, Neo4j, GCS)에서 일괄 삭제한다."""
    try:
        UUID(doc_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="유효하지 않은 doc_id 형식")

    session_factory = _get_session_factory()
    async with session_factory() as session:
        doc_result = await session.execute(
            text("""
                SELECT title, upload_status, permission_level, department_id, user_id
                FROM documents WHERE doc_id = :doc_id
            """),
            {"doc_id": doc_id},
        )
        doc_row = doc_result.mappings().fetchone()

    if doc_row is None:
        raise HTTPException(status_code=404, detail=f"문서를 찾을 수 없음: {doc_id}")

    perm = doc_row["permission_level"]
    owner_user = doc_row["user_id"]
    owner_dept = doc_row["department_id"]
    can_delete = (
        perm == "public"
        or (owner_dept is not None and owner_dept == current_user["team"])
        or owner_user == current_user["user_id"]
    )
    if not can_delete:
        raise HTTPException(status_code=403, detail="이 문서를 삭제할 권한이 없습니다.")

    sync_warning: str | None = None
    try:
        async with session_factory() as session:
            await sync_old_document_version(
                old_doc_id=doc_id,
                session=session,
                delete_gcs=True,
                delete_neo4j=True,
            )
    except Exception as e:
        logger.error(f"[delete_document] sync 실패 doc_id={doc_id}: {e}")
        sync_warning = f"PG 삭제 완료. 외부 저장소(Neo4j/GCS) 동기화 실패: {e}"

    return DeleteDocumentResponse(
        doc_id=doc_id,
        status="deleted",
        sync_warning=sync_warning,
    )


@router.get("/stats", response_model=KmsStatsResponse)
async def get_kms_stats() -> KmsStatsResponse:
    """agent_traces 집계 — 전체 성공률과 스테이지별 평균 처리시간을 반환한다."""
    session_factory = _get_session_factory()
    async with session_factory() as session:
        overview_result = await session.execute(
            text("""
                SELECT
                    COUNT(*)                                       AS total_runs,
                    COUNT(*) FILTER (WHERE status = 'success')    AS success_count,
                    COUNT(*) FILTER (WHERE status = 'fail')       AS fail_count
                FROM agent_traces
            """)
        )
        overview = overview_result.mappings().fetchone()

        stage_result = await session.execute(
            text("""
                SELECT
                    agent_name,
                    AVG(execution_ms)::float  AS avg_execution_ms,
                    COUNT(*)::int             AS run_count
                FROM agent_traces
                GROUP BY agent_name
                ORDER BY agent_name
            """)
        )
        stage_rows = stage_result.mappings().fetchall()

    total = overview["total_runs"] if overview else 0
    success = overview["success_count"] if overview else 0
    fail = overview["fail_count"] if overview else 0
    rate = success / total if total > 0 else 0.0

    stage_stats = [
        StageStatItem(
            agent_name=r["agent_name"],
            avg_execution_ms=r["avg_execution_ms"] or 0.0,
            run_count=r["run_count"],
        )
        for r in stage_rows
    ]

    return KmsStatsResponse(
        total_runs=total,
        success_count=success,
        fail_count=fail,
        success_rate=rate,
        stage_stats=stage_stats,
    )


_NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
_NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
_NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

_CYPHER_DOC_ENTITIES = """\
MATCH (d:Document {doc_id: $doc_id})-[:COVERS]->(e:Entity)
RETURN e.name AS name, e.type AS type, e.description AS description"""


async def _run_neo4j_cypher(cypher: str, params: dict | None = None) -> list[dict]:
    try:
        from neo4j import AsyncGraphDatabase
    except ImportError:
        logger.warning("neo4j 패키지 미설치 — Neo4j 조회 건너뜁니다.")
        return []

    driver = AsyncGraphDatabase.driver(_NEO4J_URI, auth=(_NEO4J_USER, _NEO4J_PASSWORD))
    try:
        async with driver.session() as session:
            result = await session.run(cypher, parameters=params or {})
            return [dict(record) async for record in result]
    finally:
        await driver.close()


@router.get("/docs/{doc_id}/entities", response_model=DocEntitiesResponse)
async def get_doc_entities(doc_id: str) -> DocEntitiesResponse:
    """Stage 6에서 Neo4j에 저장된 문서 엔티티 목록을 반환한다."""
    try:
        UUID(doc_id)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"유효하지 않은 doc_id 형식: {doc_id}")

    try:
        records = await _run_neo4j_cypher(_CYPHER_DOC_ENTITIES, {"doc_id": doc_id})
    except Exception as e:
        logger.warning(f"Neo4j 엔티티 조회 실패 doc_id={doc_id}: {e}")
        records = []

    entities = [
        EntityItem(
            name=r["name"],
            type=r.get("type"),
            description=r.get("description"),
        )
        for r in records
        if r.get("name")
    ]

    return DocEntitiesResponse(doc_id=doc_id, entities=entities, total=len(entities))


_CYPHER_RELATED_DOCS = """\
MATCH (d:Document {doc_id: $doc_id})-[:COVERS]->(e:Entity)<-[:COVERS]-(r:Document)
WHERE r.doc_id <> $doc_id
WITH r, COUNT(e) AS shared_count
ORDER BY shared_count DESC
LIMIT 3
RETURN r.doc_id AS doc_id, r.title AS title, r.category AS category, shared_count"""


@router.get("/docs/{doc_id}/stats", response_model=DocStatsResponse)
async def get_doc_stats(
    doc_id: str,
    current_user: dict = Depends(get_current_kms_user),
) -> DocStatsResponse:
    """문서 RAG 활용 통계 — rag_references 기반 참조 횟수, 최근 사용 시각, 최근 7일 활용 여부."""
    try:
        UUID(doc_id)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"유효하지 않은 doc_id 형식: {doc_id}")

    team_id = current_user.get("team", "")
    session_factory = _get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            text("""
                SELECT
                    COUNT(*)::int AS rag_reference_count,
                    MAX(queried_at) AS last_used_at,
                    BOOL_OR(queried_at >= NOW() - INTERVAL '7 days') AS recent_search_reflected
                FROM rag_references
                WHERE doc_id = CAST(:doc_id AS uuid)
                  AND team_id = :team_id
            """),
            {"doc_id": doc_id, "team_id": team_id},
        )
        row = result.mappings().fetchone()

    count = int(row["rag_reference_count"]) if row else 0
    last_used = row["last_used_at"].isoformat() if row and row["last_used_at"] else None
    reflected = bool(row["recent_search_reflected"]) if row else False

    return DocStatsResponse(
        doc_id=doc_id,
        rag_reference_count=count,
        last_used_at=last_used,
        recent_search_reflected=reflected,
    )


@router.get("/docs/{doc_id}/related", response_model=DocRelatedResponse)
async def get_doc_related(
    doc_id: str,
    current_user: dict = Depends(get_current_kms_user),
) -> DocRelatedResponse:
    """Neo4j 공유 엔티티 기반 연관 문서 최대 3개 반환. Neo4j 오프라인 시 빈 목록 반환."""
    try:
        UUID(doc_id)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"유효하지 않은 doc_id 형식: {doc_id}")

    try:
        records = await _run_neo4j_cypher(_CYPHER_RELATED_DOCS, {"doc_id": doc_id})
    except Exception as e:
        logger.warning(f"연관 문서 Neo4j 조회 실패 doc_id={doc_id}: {e}")
        records = []

    related = [
        RelatedDocItem(
            doc_id=r["doc_id"],
            title=r.get("title"),
            category=r.get("category"),
            shared_count=int(r.get("shared_count", 0)),
        )
        for r in records
        if r.get("doc_id")
    ]

    return DocRelatedResponse(doc_id=doc_id, related=related, total=len(related))


async def _embed_query(query_text: str) -> list[float]:
    """쿼리 텍스트를 Ollama bge-m3로 임베딩한다."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{_OLLAMA_BASE_URL}/api/embeddings",
            json={"model": _EMBEDDING_MODEL, "prompt": query_text},
        )
        response.raise_for_status()
        return response.json()["embedding"]


@router.get("/docs/{doc_id}/page-images")
async def list_doc_page_images(doc_id: str) -> list[dict]:
    """문서의 파싱 페이지 이미지 목록 반환.

    Storage.list_prefix()로 images/{doc_id}/ 아래 모든 경로를 한 번에 조회한다.
    기존 문서(page_count 없음)에도 동작하며 GCS 순차 탐색(최대 500회) 대비 1-call로 처리.
    """
    storage = _get_storage()
    prefix = f"images/{doc_id}/"
    all_paths = await storage.list_prefix(prefix)
    # page_N.png 형식만 추출하고 페이지 번호 순서로 정렬
    pages = []
    for path in all_paths:
        name = path.split("/")[-1]  # page_N.png
        if name.startswith("page_") and name.endswith(".png"):
            try:
                page_num = int(name[5:-4])
                pages.append((page_num, path))
            except ValueError:
                continue
    pages.sort(key=lambda x: x[0])
    return [{"page": pn, "url": f"/kms/docs/{doc_id}/page/{pn}"} for pn, _ in pages]


@router.get("/docs/{doc_id}/page/{page_num}")
async def get_doc_page_image(doc_id: str, page_num: int):
    """특정 페이지 이미지를 바이트로 반환한다."""
    from fastapi.responses import Response as FastAPIResponse

    storage = _get_storage()
    path = f"images/{doc_id}/page_{page_num}.png"

    try:
        img_bytes = await storage.load(path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"페이지 {page_num} 이미지 없음")
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Storage 오류: {e}")

    return FastAPIResponse(content=img_bytes, media_type="image/png")


# ---------------------------------------------------------------------------
# 중복 감지 엔드포인트
# ---------------------------------------------------------------------------

async def check_duplicate(
    file_hash: str,
    original_filename: str,
    session: AsyncSession,
) -> dict:
    """
    SHA256 hash + filename 기반 중복 케이스 판별.

    반환:
      { "status": "identical" | "modified" | "new", "existing_doc": {...} | None }
    """
    # 1차: 동일 hash 조회
    result = await session.execute(
        text("""
            SELECT doc_id, original_filename, upload_status, created_at
            FROM documents
            WHERE file_hash = :file_hash
              AND upload_status NOT IN ('failed', 'rejected')
            ORDER BY created_at DESC
            LIMIT 1
        """),
        {"file_hash": file_hash},
    )
    row = result.fetchone()
    if row:
        return {
            "status": "identical",
            "existing_doc": {
                "doc_id": row[0],
                "original_filename": row[1],
                "upload_status": row[2],
                "created_at": str(row[3]) if row[3] else None,
            },
        }

    # 2차: 동일 파일명 조회 (hash 다름 → 수정본)
    result2 = await session.execute(
        text("""
            SELECT doc_id, original_filename, upload_status, created_at
            FROM documents
            WHERE original_filename = :filename
              AND upload_status NOT IN ('failed', 'rejected')
            ORDER BY created_at DESC
            LIMIT 1
        """),
        {"filename": original_filename},
    )
    row2 = result2.fetchone()
    if row2:
        return {
            "status": "modified",
            "existing_doc": {
                "doc_id": row2[0],
                "original_filename": row2[1],
                "upload_status": row2[2],
                "created_at": str(row2[3]) if row2[3] else None,
            },
        }

    return {"status": "new", "existing_doc": None}


@router.post("/check-duplicate", response_model=CheckDuplicateResponse)
async def check_duplicate_endpoint(
    file_hash: str = Form(...),
    original_filename: str = Form(...),
    current_user: dict = Depends(get_current_kms_user),
) -> CheckDuplicateResponse:
    """업로드 전 SHA256 해시 기반 중복 여부를 확인한다."""
    session_factory = _get_session_factory()
    async with session_factory() as session:
        result = await check_duplicate(file_hash, original_filename, session)
    existing = (
        DuplicateExistingDoc(**result["existing_doc"])
        if result.get("existing_doc")
        else None
    )
    return CheckDuplicateResponse(status=result["status"], existing_doc=existing)


@router.post("/replace-document", response_model=ReplaceDocumentResponse)
async def replace_document(
    background_tasks: BackgroundTasks,
    old_doc_id: str = Form(...),
    file: UploadFile = File(...),
    file_hash: str | None = Form(default=None),
    source: str = Form(default="upload"),
    permission_level: str = Form(default="public"),
    visibility: str = Form(default="all"),
    current_user: dict = Depends(get_current_kms_user),
) -> ReplaceDocumentResponse:
    """기존 문서를 새 버전으로 교체한다. Graph Sync Agent로 이전 버전을 정리 후 새 파이프라인을 실행한다."""
    from app.pipeline.graph_sync import sync_old_document_version

    filename = file.filename or "unknown"
    ext = Path(filename).suffix.lstrip(".").lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"지원하지 않는 파일 형식: .{ext}",
        )

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"파일 크기 초과: {len(content) // (1024 * 1024)}MB",
        )

    new_doc_id = str(uuid4())
    session_factory = _get_session_factory()

    # 이전 버전 정리 (PG + Neo4j + GCS)
    async with session_factory() as session:
        await sync_old_document_version(
            old_doc_id=old_doc_id,
            session=session,
            delete_gcs=True,
            delete_neo4j=True,
        )

    # 새 문서 초기 레코드 삽입
    try:
        async with session_factory() as session:
            await session.execute(
                text("""
                    INSERT INTO documents
                        (doc_id, title, source, file_type, original_filename, upload_status, created_at)
                    VALUES
                        (:doc_id, :title, :source, :file_type, :original_filename, 'processing', NOW())
                    ON CONFLICT (doc_id) DO NOTHING
                """),
                {
                    "doc_id": new_doc_id,
                    "title": filename,
                    "source": source,
                    "file_type": ext,
                    "original_filename": filename,
                },
            )
            await session.commit()
    except (ConnectionRefusedError, OSError) as e:
        raise HTTPException(status_code=503, detail=f"DB 연결 실패: {e}")

    with tempfile.NamedTemporaryFile(
        delete=False, suffix=f".{ext}", prefix=f"kms_{new_doc_id}_"
    ) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    initial_state = _build_initial_state(
        new_doc_id, source, tmp_path, ext, filename,
        department_id=current_user["team"],
        user_id=current_user["user_id"],
        permission_level=permission_level,
        visibility=visibility,
        file_hash=file_hash,
    )
    background_tasks.add_task(_run_pipeline_background, initial_state)

    return ReplaceDocumentResponse(
        new_doc_id=new_doc_id,
        old_doc_id=old_doc_id,
        status="processing",
        message=f"기존 문서 {old_doc_id} 정리 완료. 새 문서 {new_doc_id} 처리 중.",
    )
