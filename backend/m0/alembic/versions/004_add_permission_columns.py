"""add RBAC permission metadata columns

Revision ID: 004
Revises: 003
Create Date: 2026-06-10

기존 컬럼은 변경하지 않는다. 아래 컬럼만 추가한다:
  documents: department_id, user_id, permission_level, visibility
  chunks:    department_id, permission_level

기본값:
  permission_level = 'public'  (기존 문서 하위호환 — RAG 검색 유지)
  visibility       = 'all'     (기존 문서 검색 노출 유지)
  department_id    = NULL      (전사 공개)
  user_id          = NULL      (시스템 업로드)
"""
from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # documents — 4개 추가
    op.add_column(
        "documents",
        sa.Column("department_id", sa.String(100), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("user_id", sa.String(100), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column(
            "permission_level",
            sa.String(20),
            nullable=False,
            server_default="public",
        ),
    )
    op.add_column(
        "documents",
        sa.Column(
            "visibility",
            sa.String(20),
            nullable=False,
            server_default="all",
        ),
    )

    # chunks — 2개 추가 (user_id 없음 — 청크 단위 소유자 불필요)
    op.add_column(
        "chunks",
        sa.Column("department_id", sa.String(100), nullable=True),
    )
    op.add_column(
        "chunks",
        sa.Column(
            "permission_level",
            sa.String(20),
            nullable=False,
            server_default="public",
        ),
    )

    # 검색 필터링 성능을 위한 인덱스
    op.create_index(
        "ix_documents_department_id",
        "documents",
        ["department_id"],
    )
    op.create_index(
        "ix_chunks_department_id",
        "chunks",
        ["department_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_chunks_department_id", table_name="chunks")
    op.drop_index("ix_documents_department_id", table_name="documents")

    op.drop_column("chunks", "permission_level")
    op.drop_column("chunks", "department_id")

    op.drop_column("documents", "visibility")
    op.drop_column("documents", "permission_level")
    op.drop_column("documents", "user_id")
    op.drop_column("documents", "department_id")
