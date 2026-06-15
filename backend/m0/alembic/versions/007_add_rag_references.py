"""add rag_references table for RAG query analytics

Revision ID: 007
Revises: 006
Create Date: 2026-06-12

chat POST /chat에서 pgvector 소스로 참조된 문서를 기록한다.
GET /kms/docs/{id}/stats에서 활용 통계를 제공하는 데 사용된다.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rag_references",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "doc_id",
            UUID(as_uuid=True),
            sa.ForeignKey("documents.doc_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chunk_id",
            UUID(as_uuid=True),
            sa.ForeignKey("chunks.chunk_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("team_id", sa.Text, nullable=False, server_default=""),
        sa.Column(
            "queried_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index(
        "ix_rag_references_doc_queried",
        "rag_references",
        ["doc_id", "queried_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_rag_references_doc_queried", table_name="rag_references")
    op.drop_table("rag_references")
