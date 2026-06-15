"""
KMS 문서 처리 파이프라인 — 공통 데이터 모델

LangGraph StateGraph에서 사용하는 DocPipelineState와
파이프라인 단계 간 전달되는 모델을 정의한다.
"""

from __future__ import annotations

from typing import Literal, Optional
from typing_extensions import TypedDict
from uuid import UUID

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# 청크 모델
# ---------------------------------------------------------------------------

class ChunkItem(TypedDict):
    chunk_id: str
    doc_id: str
    parent_chunk_id: Optional[str]     # None이면 Parent 청크
    chunk_type: Literal["parent", "child"]
    content: str
    token_count: int
    page_number: Optional[int]
    section_header: Optional[str]      # "3.2 API 설계 원칙"
    chunk_index: Optional[int]         # 문서 내 청크 순서 (0-based)


# ---------------------------------------------------------------------------
# 메타데이터 모델
# ---------------------------------------------------------------------------

class DocumentMetadata(TypedDict):
    title: str
    category: str                       # "코딩컨벤션 | 아키텍처 | 온보딩"
    team: Optional[str]                 # "백엔드팀 | 인프라팀"
    author: Optional[str]
    tags: list[str]
    source: str                         # "upload | notion | confluence | slack"


# ---------------------------------------------------------------------------
# Neo4j 저장용 관계 모델
# ---------------------------------------------------------------------------

class Neo4jEntity(BaseModel):
    name: str
    entity_type: str                    # "Technology | Pattern | Concept"
    description: Optional[str] = None


class Neo4jRelation(BaseModel):
    from_chunk_id: str
    entity_name: str
    relation_type: str = "MENTIONS"


# ---------------------------------------------------------------------------
# 저장 경로 모델
# ---------------------------------------------------------------------------

class StoragePaths(TypedDict):
    original: str                       # 원본 파일 경로
    markdown: str                       # 변환된 Markdown 파일 경로
    page_images: list[str]              # 페이지별 이미지 경로 (images/{doc_id}/page_N.png)


# ---------------------------------------------------------------------------
# LangGraph State — 파이프라인 전체 공유 상태
# ---------------------------------------------------------------------------

class DocPipelineState(TypedDict):
    # 입력 (파이프라인 진입 시 채움)
    doc_id: str                         # UUID str
    source: str                         # "upload | notion | confluence | slack"
    file_path: str                      # 업로드된 원본 파일의 로컬 경로
    file_type: str                      # "pdf | docx | pptx | txt | md"
    original_filename: str

    # Stage 1: Document Parser Agent 출력
    raw_markdown: Optional[str]
    markdown_storage_path: Optional[str]
    parser_used: Optional[str]           # "direct_read|python_docx|unstructured|pymupdf|hitl_required"
    parser_quality_score: Optional[int]  # 0~100 규칙 기반 점수 (Stage 2 quality_score와 별도)
    doc_complexity: Optional[str]        # "LOW|MEDIUM|HIGH"
    has_tables: Optional[bool]
    has_images: Optional[bool]
    page_count: Optional[int]
    parsing_time_ms: Optional[int]
    parser_warnings: Optional[list]
    fallback_used: Optional[bool]
    image_refs: Optional[list]           # GCS 이미지 경로 (Stage 6 업로드 후)
    image_data: Optional[list]           # 임시 이미지 바이너리 (Stage 1→6 전달용)
    # 형식: [{"page_number": int, "image_bytes": bytes}, ...]
    page_images: Optional[list]          # 페이지별 PNG bytes (Stage 1 추출 → Stage 6 GCS 저장)
    page_image_paths: Optional[list[str]]  # Stage 1에서 GCS에 저장한 경로 목록 → Stage 6에서 재사용

    # Stage 2: Markdown 검증 출력
    validated_markdown: Optional[str]
    quality_score: Optional[float]      # 0.0 ~ 1.0
    quality_issues: Optional[list[str]]
    hitl_required: bool

    # Stage 3: 청킹 출력
    chunks: Optional[list[ChunkItem]]

    # Stage 4: Chunk 검증 출력
    chunk_validation_passed: bool
    chunk_validation_issues: Optional[list[str]]

    # Stage 5: 메타데이터 추출 출력
    metadata: Optional[DocumentMetadata]
    neo4j_entities: Optional[list[dict]]
    neo4j_relations: Optional[list[dict]]
    category_reasoning: Optional[str]
    category_is_new: Optional[bool]
    category_alternatives: Optional[list[str]]
    stage5_latency_ms: Optional[int]       # Gemini LLM 호출 소요 시간 (ms)

    # Stage 5b: 메타데이터 검증 출력
    metadata_valid: Optional[bool]
    metadata_score: Optional[float]
    metadata_issues: Optional[list[str]]

    # Stage 6: 저장 & 라우팅 출력
    stored: bool
    neo4j_stored: Optional[bool]        # None=미실행, True=성공, False=실패(stored_partial)
    storage_paths: Optional[StoragePaths]

    # RBAC 권한 메타데이터 (업로드 시 선택적으로 전달 — 없으면 Stage 6에서 기본값 적용)
    department_id: Optional[str]
    user_id: Optional[str]
    permission_level: Optional[str]     # 'public' | 'team' | 'private'
    visibility: Optional[str]           # 'all' | 'department' | 'owner'
    # SHA256 hex digest — 중복 감지용 (프론트에서 계산 후 전달)
    file_hash: Optional[str]

    # 파이프라인 제어
    status: str                         # "processing|validated|stored|stored_partial|failed|hitl_pending"
    error: Optional[str]
    current_stage: str


# ---------------------------------------------------------------------------
# 재처리 state 팩토리
# ---------------------------------------------------------------------------

def make_reprocess_state(
    doc_id: str,
    raw_markdown: str,
    markdown_path: Optional[str] = None,
    start_validated: bool = False,
) -> DocPipelineState:
    """
    HITL 재처리용 DocPipelineState를 안전하게 생성한다.
    file_path / file_type 등 원본 파일 관련 필드는 비워두고,
    stage6에서 기존 storage_paths를 재사용한다.
    """
    return DocPipelineState(
        doc_id=doc_id,
        source="reprocess",
        file_path="",
        file_type="",
        original_filename="",
        raw_markdown=raw_markdown,
        markdown_storage_path=markdown_path,
        parser_used=None,
        parser_quality_score=None,
        doc_complexity=None,
        has_tables=None,
        has_images=None,
        page_count=None,
        parsing_time_ms=None,
        parser_warnings=None,
        fallback_used=None,
        image_refs=None,
        image_data=None,
        page_images=None,
        validated_markdown=raw_markdown if start_validated else None,
        quality_score=None,
        quality_issues=None,
        hitl_required=False,
        chunks=None,
        chunk_validation_passed=False,
        chunk_validation_issues=None,
        metadata=None,
        neo4j_entities=None,
        neo4j_relations=None,
        category_reasoning=None,
        category_is_new=False,
        category_alternatives=[],
        metadata_valid=None,
        metadata_score=None,
        metadata_issues=None,
        stored=False,
        neo4j_stored=None,
        storage_paths=None,
        status="processing",
        error=None,
        current_stage="reprocess_init",
    )
