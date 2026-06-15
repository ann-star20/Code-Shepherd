"""add metadata_score to documents

Revision ID: 009
Revises: 008
Create Date: 2026-06-14

documents.metadata_score: Stage 5b 메타데이터 검증 품질 점수 (0.0~1.0).
Stage 6 저장 시 기록하여 SQL로 문서별 메타데이터 품질을 직접 조회할 수 있도록 한다.
"""
from alembic import op
import sqlalchemy as sa

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("metadata_score", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("documents", "metadata_score")
