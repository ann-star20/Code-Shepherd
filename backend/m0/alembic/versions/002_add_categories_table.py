"""add categories table for KB Evolution

Revision ID: 002
Revises: 001
Create Date: 2026-06-08

categories: KB Evolution에서 동적으로 카테고리를 추가/조회하기 위한 테이블.
_category_definitions.py의 하드코딩 frozenset을 DB 기반으로 확장한다.
"""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    # 기존 하드코딩 카테고리를 초기 데이터로 삽입
    op.execute("""
        INSERT INTO categories (name, description) VALUES
        ('코딩컨벤션', '코딩 스타일, 네이밍 규칙, 코드 품질 가이드, 개발 표준'),
        ('아키텍처',   'SW 설계, 시스템 구조, 아키텍처 패턴, API 설계, 데이터 모델링'),
        ('온보딩',     '신입 교육, 입문 가이드, 개발 환경 설정, 팀 규칙 안내'),
        ('보안',       '보안 취약점, 인증·인가, 데이터 보호, 보안 정책'),
        ('배포',       'CI/CD, 배포 프로세스, Docker, Kubernetes, 인프라 운영'),
        ('기타',       '위 카테고리에 명확히 해당하지 않는 경우에만 선택')
        ON CONFLICT (name) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_table("categories")
