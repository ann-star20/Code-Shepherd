"""curriculum_plan에 completed_at 컬럼 추가 (POST /api/complete, D11)

status='completed'(카드 생성 성공 여부)와는 별개로, 사용자가 카드를 실제로
학습 완료한 시각을 기록하기 위한 컬럼.

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import TIMESTAMP

TZ = TIMESTAMP(timezone=True)

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("curriculum_plan", sa.Column("completed_at", TZ, nullable=True))


def downgrade() -> None:
    op.drop_column("curriculum_plan", "completed_at")
