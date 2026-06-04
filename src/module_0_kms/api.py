"""
KMS FastAPI 라우터

엔드포인트:
    POST /kms/upload                    문서 업로드 → 파이프라인 실행
    GET  /kms/status/{doc_id}           처리 상태 조회
    GET  /kms/docs                      문서 목록 조회 (status 필터, 페이지네이션)
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

import asyncpg
import httpx
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from module_0_kms.pipeline.models import DocPipelineState

_OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "bge-m3")

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/kms", tags=["KMS"])

SUPPORTED_EXTENSIONS = {"pdf", "docx", "pptx", "txt", "md"}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB

ALLOWED_DOC_STATUSES = {
    "processing", "stored", "stored_partial", "failed",
    "hitl_pending", "rejected", "reprocess_failed", "reprocessing",
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


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultItem]
    total: int


class AgentTraceItem(BaseModel):
    trace_id: str
    agent_name: str
    status: str
    started_at: str | None = None
    ended_at: str | None = None
    execution_ms: int | None = None
    error_message: str | None = None


class ChunkItem(BaseModel):
    chunk_id: str
    chunk_type: str
    content: str
    token_count: int | None = None
    section_header: str | None = None
    page_number: int | None = None


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


# ---------------------------------------------------------------------------
# 의존성 — main.py lifespan에서 주입
# ---------------------------------------------------------------------------

_db_pool: asyncpg.Pool | None = None
_pipeline = None  # LangGraph compiled graph, lifespan에서 싱글턴으로 주입
_storage = None   # Storage 구현체, lifespan에서 싱글턴으로 주입


def _get_pool() -> asyncpg.Pool:
    if _db_pool is None:
        raise RuntimeError("DB 풀이 초기화되지 않았습니다. lifespan을 확인하세요.")
    return _db_pool


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

    # Content-Length 선행 검사 — 파일 본문을 읽기 전에 413 반환 (메모리 spike 방지)
    if file.size is not None and file.size > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"파일 크기 초과: {file.size // (1024 * 1024)}MB. 최대 {MAX_UPLOAD_BYTES // (1024 * 1024)}MB",
        )

    # Content-Length 미전송 시 폴백: 읽은 후 크기 검사
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"파일 크기 초과: {len(content) // (1024 * 1024)}MB. 최대 {MAX_UPLOAD_BYTES // (1024 * 1024)}MB",
        )

    doc_id = str(uuid4())
    pool = _get_pool()
    _get_pipeline()

    # hitl_queue가 documents(doc_id)를 FK로 참조하므로 파이프라인 전 초기 레코드 삽입
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO documents (doc_id, title, source, file_type, original_filename, upload_status, created_at)
                VALUES ($1, $2, $3, $4, $5, 'processing', NOW())
                ON CONFLICT (doc_id) DO NOTHING
                """,
                UUID(doc_id),
                filename,
                source,
                ext,
                filename,
            )
    except (ConnectionRefusedError, OSError) as e:
        logger.error(f"DB 연결 실패: {e}")
        raise HTTPException(
            status_code=503,
            detail="DB 연결 실패 — 잠시 후 다시 시도하세요. 문제가 지속되면 관리자에게 문의하세요.",
        )

    # 임시 파일에 업로드 내용 저장
    with tempfile.NamedTemporaryFile(
        delete=False, suffix=f".{ext}", prefix=f"kms_{doc_id}_"
    ) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    initial_state = _build_initial_state(doc_id, source, tmp_path, ext, filename)
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
    }


async def _run_pipeline_background(initial_state: DocPipelineState) -> None:
    doc_id = initial_state["doc_id"]
    tmp_path = initial_state["file_path"]
    try:
        result: DocPipelineState = await _get_pipeline().ainvoke(initial_state)
        # ainvoke 반환 시점 = 모든 LangGraph 노드(하네스 포함) 완료 시점.
        # 이 이후에 upload_status 를 설정해야 agent_traces 가 모두 기록된 상태에서
        # 프론트엔드가 '완료'를 감지한다. (race condition 방지)
        final_status = result.get("status", "failed")
        await _update_document_status(doc_id, final_status, result)
    except Exception as e:
        logger.error(f"파이프라인 실행 실패: {e}", extra={"doc_id": doc_id})
        await _update_document_status(doc_id, "failed")
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            logger.warning("임시 파일 정리 실패", extra={"doc_id": doc_id, "path": tmp_path})


async def _update_document_status(
    doc_id: str,
    status: str,
    state: dict | None = None,
) -> None:
    async with _get_pool().acquire() as conn:
        if state and any(state.get(k) for k in ("parser_used", "doc_complexity", "parsing_time_ms")):
            await conn.execute(
                """UPDATE documents
                   SET upload_status   = $1,
                       parser_used     = COALESCE($2, parser_used),
                       doc_complexity  = COALESCE($3, doc_complexity),
                       parsing_time_ms = COALESCE($4, parsing_time_ms)
                   WHERE doc_id = $5""",
                status,
                state.get("parser_used"),
                state.get("doc_complexity"),
                state.get("parsing_time_ms"),
                UUID(doc_id),
            )
        else:
            await conn.execute(
                "UPDATE documents SET upload_status = $1 WHERE doc_id = $2",
                status,
                UUID(doc_id),
            )


@router.get("/status/{doc_id}", response_model=StatusResponse)
async def get_document_status(doc_id: str) -> StatusResponse:
    """문서 처리 상태를 조회한다. agent_traces를 포함해 파이프라인 진행 상황을 실시간 반환."""
    try:
        doc_uuid = UUID(doc_id)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"유효하지 않은 doc_id 형식: {doc_id}")

    pool = _get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT upload_status FROM documents WHERE doc_id = $1",
            doc_uuid,
        )
        if row is None:
            raise HTTPException(status_code=404, detail=f"문서를 찾을 수 없음: {doc_id}")

        trace_rows = await conn.fetch(
            """
            SELECT trace_id, agent_name, status,
                   started_at::text, ended_at::text,
                   execution_ms, error_message
            FROM agent_traces
            WHERE doc_id = $1
            ORDER BY started_at ASC NULLS LAST
            """,
            doc_uuid,
        )

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
    error_msg: str | None = None
    if upload_status == "failed":
        # 실패한 트레이스의 에러 메시지 우선 반환
        fail_row = next((r for r in trace_rows if r["status"] == "fail" and r["error_message"]), None)
        if fail_row:
            error_msg = fail_row["error_message"]
        else:
            # harness DB 업데이트 실패로 "running"이 남아있는 경우
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
) -> SearchResponse:
    """
    pgVector 코사인 유사도 검색.
    쿼리를 Ollama bge-m3로 임베딩한 뒤 가장 유사한 child chunk를 반환한다.
    """
    pool = _get_pool()

    try:
        query_embedding = await _embed_query(q)
    except Exception as e:
        logger.error(f"쿼리 임베딩 실패: {e}")
        raise HTTPException(status_code=503, detail=f"임베딩 서비스 오류: {e}")

    embedding_str = f"[{','.join(str(v) for v in query_embedding)}]"

    category_filter = ""
    params: list = [embedding_str, limit]
    if category:
        category_filter = "AND ce.metadata->>'category' = $3"
        params.append(category)

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT
                ce.chunk_id::text,
                ce.content,
                1 - (ce.embedding <=> $1::vector) AS score,
                ce.metadata,
                d.title AS doc_title
            FROM chunk_embeddings ce
            LEFT JOIN chunks c ON ce.chunk_id = c.chunk_id
            LEFT JOIN documents d ON c.doc_id = d.doc_id
            WHERE d.upload_status IN ('stored', 'stored_partial')
            {category_filter}
            ORDER BY ce.embedding <=> $1::vector
            LIMIT $2
            """,
            *params,
        )

    if not rows:
        logger.info(f"KMS 검색 결과 없음: query='{q[:50]}'")

    results = [
        SearchResultItem(
            chunk_id=row["chunk_id"],
            content=row["content"],
            score=float(row["score"]),
            metadata=row["metadata"] if isinstance(row["metadata"], dict) else None,
            doc_title=row["doc_title"],
        )
        for row in rows
    ]

    return SearchResponse(query=q, results=results, total=len(results))


@router.get("/docs", response_model=DocListResponse)
async def list_documents(
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> DocListResponse:
    """문서 목록을 조회한다. status 필터와 페이지네이션을 지원한다."""
    if limit <= 0 or limit > 100:
        raise HTTPException(status_code=422, detail=f"limit은 1~100 사이여야 합니다: {limit}")
    if offset < 0:
        raise HTTPException(status_code=422, detail=f"offset은 0 이상이어야 합니다: {offset}")
    if status is not None and status not in ALLOWED_DOC_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"허용되지 않는 status 값: '{status}'. 허용값: {sorted(ALLOWED_DOC_STATUSES)}",
        )

    pool = _get_pool()

    if status is not None:
        count_query = "SELECT COUNT(*) AS count FROM documents WHERE upload_status = $1"
        list_query = """
            SELECT doc_id::text, title, file_type, upload_status, created_at
            FROM documents
            WHERE upload_status = $1
            ORDER BY created_at DESC NULLS LAST
            LIMIT $2 OFFSET $3
        """
        count_params = (status,)
        list_params = (status, limit, offset)
    else:
        count_query = "SELECT COUNT(*) AS count FROM documents"
        list_query = """
            SELECT doc_id::text, title, file_type, upload_status, created_at
            FROM documents
            ORDER BY created_at DESC NULLS LAST
            LIMIT $1 OFFSET $2
        """
        count_params = ()
        list_params = (limit, offset)

    async with pool.acquire() as conn:
        count_row = await conn.fetchrow(count_query, *count_params)
        rows = await conn.fetch(list_query, *list_params)

    total = count_row["count"] if count_row else 0

    docs = [
        DocListItem(
            doc_id=r["doc_id"],
            title=r["title"],
            file_type=r["file_type"],
            status=r["upload_status"],
            created_at=r["created_at"].isoformat() if r["created_at"] else None,
        )
        for r in rows
    ]

    return DocListResponse(docs=docs, total=total, limit=limit, offset=offset)


@router.get("/docs/{doc_id}/markdown", response_model=MarkdownResponse)
async def get_doc_markdown(doc_id: str) -> MarkdownResponse:
    """문서의 파싱된 Markdown 원문을 Storage에서 반환한다."""
    storage = _get_storage()

    try:
        doc_uuid = UUID(doc_id)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"유효하지 않은 doc_id 형식: {doc_id}")

    pool = _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT markdown_path FROM documents WHERE doc_id = $1",
            doc_uuid,
        )

    if row is None:
        raise HTTPException(status_code=404, detail=f"문서를 찾을 수 없음: {doc_id}")

    markdown_path: str | None = row["markdown_path"]
    if not markdown_path:
        raise HTTPException(status_code=404, detail=f"문서의 Markdown이 아직 생성되지 않았습니다: {doc_id}")

    try:
        content_bytes = await storage.load(markdown_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Storage에 Markdown 파일 없음: {markdown_path}")
    except Exception as e:
        logger.error(f"Storage 로드 실패: {e}", extra={"doc_id": doc_id, "path": markdown_path})
        raise HTTPException(status_code=503, detail=f"Storage 오류: {e}")

    return MarkdownResponse(
        doc_id=doc_id,
        markdown_path=markdown_path,
        content=content_bytes.decode("utf-8", errors="replace"),
    )


@router.get("/docs/{doc_id}/metadata", response_model=DocMetadataResponse)
async def get_doc_metadata(doc_id: str) -> DocMetadataResponse:
    """Stage 5에서 추출된 문서 메타데이터를 반환한다. team·tags는 chunk_embeddings에서 읽는다."""
    try:
        uuid_id = UUID(doc_id)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"유효하지 않은 doc_id 형식: {doc_id}")

    pool = _get_pool()
    async with pool.acquire() as conn:
        doc_row = await conn.fetchrow(
            """
            SELECT title, category, source, file_type, created_at
            FROM documents WHERE doc_id = $1
            """,
            uuid_id,
        )
        if doc_row is None:
            raise HTTPException(status_code=404, detail=f"문서를 찾을 수 없음: {doc_id}")

        meta_row = await conn.fetchrow(
            """
            SELECT ce.metadata
            FROM chunk_embeddings ce
            INNER JOIN chunks c ON ce.chunk_id = c.chunk_id
            WHERE c.doc_id = $1
            LIMIT 1
            """,
            uuid_id,
        )

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
async def get_doc_details(doc_id: str) -> DocDetailsResponse:
    """에이전트 트레이스 + 청크 상세 조회."""
    pool = _get_pool()
    try:
        uuid_id = UUID(doc_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="유효하지 않은 doc_id 형식")

    async with pool.acquire() as conn:
        doc_row = await conn.fetchrow(
            """
            SELECT title, file_type, upload_status, created_at,
                   parser_used, doc_complexity, parsing_time_ms
            FROM documents WHERE doc_id = $1
            """,
            uuid_id,
        )
        if doc_row is None:
            raise HTTPException(status_code=404, detail=f"문서를 찾을 수 없음: {doc_id}")

        trace_rows = await conn.fetch(
            """
            SELECT trace_id::text, agent_name, status,
                   started_at, ended_at, execution_ms, error_message
            FROM agent_traces
            WHERE doc_id = $1
            ORDER BY started_at NULLS LAST
            """,
            uuid_id,
        )

        chunk_rows = await conn.fetch(
            """
            SELECT chunk_id::text, chunk_type, content, token_count,
                   section_header, page_number
            FROM chunks
            WHERE doc_id = $1
            ORDER BY
                CASE WHEN chunk_type = 'parent' THEN 0 ELSE 1 END,
                page_number NULLS LAST
            """,
            uuid_id,
        )

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
        quality_score=None,
        doc_complexity=doc_row["doc_complexity"],
        parsing_time_ms=doc_row["parsing_time_ms"],
        agent_traces=traces,
        chunks=chunks,
    )


@router.get("/stats", response_model=KmsStatsResponse)
async def get_kms_stats() -> KmsStatsResponse:
    """agent_traces 집계 — 전체 성공률과 스테이지별 평균 처리시간을 반환한다."""
    pool = _get_pool()
    async with pool.acquire() as conn:
        overview = await conn.fetchrow(
            """
            SELECT
                COUNT(*)                                       AS total_runs,
                COUNT(*) FILTER (WHERE status = 'success')    AS success_count,
                COUNT(*) FILTER (WHERE status = 'fail')       AS fail_count
            FROM agent_traces
            """
        )
        stage_rows = await conn.fetch(
            """
            SELECT
                agent_name,
                AVG(execution_ms)::float  AS avg_execution_ms,
                COUNT(*)::int             AS run_count
            FROM agent_traces
            GROUP BY agent_name
            ORDER BY agent_name
            """
        )

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


async def _embed_query(text: str) -> list[float]:
    """쿼리 텍스트를 Ollama bge-m3로 임베딩한다."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{_OLLAMA_BASE_URL}/api/embeddings",
            json={"model": _EMBEDDING_MODEL, "prompt": text},
        )
        response.raise_for_status()
        return response.json()["embedding"]


def _status_message(state: DocPipelineState) -> str:
    status = state.get("status", "")
    if status == "stored":
        return "문서 처리 완료 — KMS에 저장되었습니다"
    if status == "hitl_pending":
        issues = state.get("quality_issues") or state.get("chunk_validation_issues") or []
        return f"수동 검토 필요: {', '.join(issues[:2])}"
    if status == "failed":
        return f"처리 실패: {state.get('error', '알 수 없는 오류')}"
    return status
