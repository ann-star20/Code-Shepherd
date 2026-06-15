"""add file_hash column for SHA256 duplicate detection

Revision ID: 005
Revises: 004
Create Date: 2026-06-11

file_hash VARCHAR(64): SHA256 hex digest of file content.
NULL for documents uploaded before this migration.
"""
from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("file_hash", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_documents_file_hash",
        "documents",
        ["file_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_documents_file_hash", table_name="documents")
    op.drop_column("documents", "file_hash")
