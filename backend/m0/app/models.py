"""m0 SQLAlchemy ORM 모델 — documents, chunks, chunk_embeddings, agent_traces.

Alembic 마이그레이션의 target_metadata 소스.
alembic/env.py에서 이 모듈을 import해야 한다.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.db import Base

try:
    from pgvector.sqlalchemy import Vector
    _VECTOR_AVAILABLE = True
except ImportError:
    # pgvector 미설치 환경(CI 등)에서 모델 import가 깨지지 않도록 폴백
    Vector = None  # type: ignore[assignment,misc]
    _VECTOR_AVAILABLE = False


# ---------------------------------------------------------------------------
# documents
# ---------------------------------------------------------------------------

class Document(Base):
    __tablename__ = "documents"

    doc_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source: Mapped[str] = mapped_column(
        String(50), nullable=False, default="upload"
    )
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    file_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    markdown_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    upload_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="processing"
    )
    storage_synced: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    neo4j_synced: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    parser_used: Mapped[str | None] = mapped_column(String(50), nullable=True)
    doc_complexity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    parsing_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # RBAC 권한 메타데이터 — 향후 접근 제어 확장용 (현재는 저장만)
    department_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    permission_level: Mapped[str] = mapped_column(String(20), nullable=False, default="public")
    visibility: Mapped[str] = mapped_column(String(20), nullable=False, default="all")
    # 중복 감지용 SHA256 해시 (기존 문서는 NULL)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Stage 5b 메타데이터 검증 품질 점수 (0.0~1.0)
    metadata_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    chunks: Mapped[list["Chunk"]] = relationship(
        "Chunk", back_populates="document", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# chunks
# ---------------------------------------------------------------------------

class Chunk(Base):
    __tablename__ = "chunks"

    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    doc_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.doc_id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chunks.chunk_id", ondelete="SET NULL"),
        nullable=True,
    )
    chunk_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # "parent" | "child"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_header: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # RBAC 비정규화 — pgVector 필터링 시 documents JOIN 없이 바로 사용
    department_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    permission_level: Mapped[str] = mapped_column(String(20), nullable=False, default="public")

    document: Mapped["Document"] = relationship("Document", back_populates="chunks")
    embedding: Mapped["ChunkEmbedding | None"] = relationship(
        "ChunkEmbedding", back_populates="chunk", uselist=False
    )


# ---------------------------------------------------------------------------
# chunk_embeddings (pgVector)
# ---------------------------------------------------------------------------

def _embedding_column():
    """pgvector 설치 여부에 따라 컬럼 타입을 선택한다."""
    if _VECTOR_AVAILABLE:
        return mapped_column(Vector(1024), nullable=True)
    # pgvector 없는 환경: Float 배열로 폴백 (마이그레이션/실행 불가 — 개발 편의용)
    return mapped_column(Text, nullable=True)


class ChunkEmbedding(Base):
    __tablename__ = "chunk_embeddings"

    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chunks.chunk_id", ondelete="CASCADE"),
        primary_key=True,
    )
    embedding: Mapped[list[float] | None] = _embedding_column()
    model_name: Mapped[str] = mapped_column(
        String(100), nullable=False, default="bge-m3"
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )

    chunk: Mapped["Chunk"] = relationship("Chunk", back_populates="embedding")


# ---------------------------------------------------------------------------
# agent_traces
# ---------------------------------------------------------------------------

class AgentTrace(Base):
    __tablename__ = "agent_traces"

    trace_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    task_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    doc_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="running"
    )  # "running" | "success" | "fail"
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    execution_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
