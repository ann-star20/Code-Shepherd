"""team_invitations — 팀 초대 수락/거절 (additive)

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-05

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "team_invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("invitee_user_id", sa.Uuid(), nullable=False),
        sa.Column("invited_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["team_id"], ["teams.team_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invitee_user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["invited_by_user_id"], ["users.user_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'declined', 'cancelled')",
            name="ck_team_invitations_status",
        ),
    )
    op.create_index(
        "idx_team_invitations_invitee_pending",
        "team_invitations",
        ["invitee_user_id", "status"],
    )
    op.create_index(
        "idx_team_invitations_team_invitee",
        "team_invitations",
        ["team_id", "invitee_user_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_team_invitations_team_invitee", table_name="team_invitations")
    op.drop_index("idx_team_invitations_invitee_pending", table_name="team_invitations")
    op.drop_table("team_invitations")
