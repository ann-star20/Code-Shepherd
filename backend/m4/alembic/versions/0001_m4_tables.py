"""m4 신규 테이블 생성: review_issue, curriculum_plan

Revision ID: 0001
Revises:
Create Date: 2026-06-06
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import TIMESTAMP

TZ = TIMESTAMP(timezone=True)

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. review_issue — 코딩 에이전트 인풋 저장
    # pull_request_id, user_id는 nullable: Phase 1 mock 데이터 사용 시 None 허용
    op.create_table(
        "review_issue",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("pull_request_id", UUID(as_uuid=True), sa.ForeignKey("pull_requests.id", ondelete="SET NULL"), nullable=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("github_id", sa.Text),
        sa.Column("agent", sa.Text),
        sa.Column("severity", sa.Text, nullable=False),
        sa.Column("keyword", sa.Text, nullable=False),
        sa.Column("sub_category", sa.Text),
        sa.Column("code_context", sa.Text),
        sa.Column("code_snippet", sa.Text),   # nullable — 없으면 before_code=null
        sa.Column("suggestion", sa.Text),
        sa.Column("programming_language", sa.Text),
        sa.Column("framework", sa.Text),
        sa.Column("framework_version", sa.Text),
        sa.Column("name_of_function", sa.Text),
        sa.Column("created_at", TZ, nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("severity IN ('critical','high','medium','low')", name="ck_review_issue_severity"),
    )
    op.create_index("idx_review_issue_pull_request_id", "review_issue", ["pull_request_id"])
    op.create_index("idx_review_issue_user_keyword", "review_issue", ["user_id", "keyword"])

    # 2. curriculum_plan — 학습 카드 단위 저장
    op.create_table(
        "curriculum_plan",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("issue_id", UUID(as_uuid=True), sa.ForeignKey("review_issue.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("llm_fallback", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("error_message", sa.Text),          # 실패 시 오류 메시지
        sa.Column("card_content", JSONB),              # status=completed일 때 채워짐
        sa.Column("created_at", TZ, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", TZ, nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('pending','running','completed','failed')", name="ck_curriculum_plan_status"),
    )
    op.create_index("idx_curriculum_plan_status", "curriculum_plan", ["status"])


def downgrade() -> None:
    op.drop_table("curriculum_plan")
    op.drop_table("review_issue")
