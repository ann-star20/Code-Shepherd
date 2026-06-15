"""add error_message column to documents

Revision ID: 008
Revises: 007
Create Date: 2026-06-13

파이프라인 예외 발생 시 에러 메시지를 documents 테이블에 직접 저장한다.
기존 방식(agent_traces 역추적)으로는 첫 trace 작성 전 크래시 시 에러 원인을 알 수 없었다.
"""

from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("error_message", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("documents", "error_message")
