"""add quality_score to documents

Revision ID: 003
Revises: 002
Create Date: 2026-06-09

documents.quality_score: Stage 2 마크다운 검증 품질 점수 (0.0~1.0).
성공 경로에서도 저장하여 /kms/docs/{id}/details API로 반환할 수 있도록 한다.
"""
from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("quality_score", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("documents", "quality_score")
