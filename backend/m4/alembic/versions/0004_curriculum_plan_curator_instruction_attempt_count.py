"""curriculum_plan에 curator_instruction/attempt_count 컬럼 추가 (T16, D22)

Curator Agent가 카드 생성에 사용한 마지막 지시(curator_instruction)와 build_card
시도 횟수(attempt_count, D26 재시도 포함)를 기록한다.

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-13
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("curriculum_plan", sa.Column("curator_instruction", JSONB(), nullable=True))
    op.add_column(
        "curriculum_plan",
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("curriculum_plan", "attempt_count")
    op.drop_column("curriculum_plan", "curator_instruction")
