"""add chunk_index to chunks table

Revision ID: 001
Revises:
Create Date: 2026-06-07

chunk_index: 문서 내 청크 삽입 순서를 보장하는 정수 컬럼.
page_number가 NULL인 DOCX/TXT 문서에서 파싱 미리보기 순서가 뒤섞이는
문제를 해결한다.

기존 청크: ctid 기반 ROW_NUMBER로 역순 없이 백필.
"""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chunks",
        sa.Column("chunk_index", sa.Integer(), nullable=True),
    )

    # 기존 청크 백필: doc_id 그룹 내 ctid 순서로 0-based index 부여
    op.execute("""
        WITH numbered AS (
            SELECT
                chunk_id,
                ROW_NUMBER() OVER (
                    PARTITION BY doc_id
                    ORDER BY ctid
                ) - 1 AS idx
            FROM chunks
        )
        UPDATE chunks c
        SET chunk_index = n.idx
        FROM numbered n
        WHERE c.chunk_id = n.chunk_id
    """)


def downgrade() -> None:
    op.drop_column("chunks", "chunk_index")
