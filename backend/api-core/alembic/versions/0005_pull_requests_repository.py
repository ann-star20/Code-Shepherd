"""pull_requests.repository_full_name — webhook upsert key (additive)

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-05

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # GCP may already have pull_requests from ddl.md without this column.
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "pull_requests" not in insp.get_table_names():
        op.create_table(
            "pull_requests",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("week_id", sa.Uuid(), nullable=True),
            sa.Column("repository_full_name", sa.String(255), nullable=False),
            sa.Column("github_pr_url", sa.Text(), nullable=True),
            sa.Column("github_pr_number", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="open"),
            sa.Column("coverage", sa.Float(), nullable=False, server_default="0"),
            sa.Column("is_lgtm", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column(
                "submitted_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "repository_full_name",
                "github_pr_number",
                name="uq_pull_requests_repo_number",
            ),
        )
        op.create_index("idx_pull_requests_user", "pull_requests", ["user_id"])
        return

    cols = {c["name"] for c in insp.get_columns("pull_requests")}
    if "repository_full_name" not in cols:
        op.add_column(
            "pull_requests",
            sa.Column("repository_full_name", sa.String(255), nullable=True),
        )
        op.execute(
            "UPDATE pull_requests SET repository_full_name = '' "
            "WHERE repository_full_name IS NULL"
        )
        op.alter_column("pull_requests", "repository_full_name", nullable=False)

    indexes = {i["name"] for i in insp.get_indexes("pull_requests")}
    if "uq_pull_requests_repo_number" not in indexes:
        op.create_unique_constraint(
            "uq_pull_requests_repo_number",
            "pull_requests",
            ["repository_full_name", "github_pr_number"],
        )


def downgrade() -> None:
    op.drop_constraint("uq_pull_requests_repo_number", "pull_requests", type_="unique")
    op.drop_column("pull_requests", "repository_full_name")
