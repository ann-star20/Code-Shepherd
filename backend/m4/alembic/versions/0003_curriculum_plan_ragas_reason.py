"""curriculum_plan에 ragas_reason 컬럼 추가 (T12 — RAGAS 평가 실패 원인 기록, D14)

RAGAS 평가가 통과하지 못했을 때의 마지막 시도 실패 원인을 기록한다.
"low_faithfulness" | "low_relevancy" | null(통과 또는 RAGAS 미실행)

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-11
"""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("curriculum_plan", sa.Column("ragas_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("curriculum_plan", "ragas_reason")
