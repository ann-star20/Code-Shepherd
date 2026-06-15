"""add extended categories — AI_ML, 프로젝트관리, 코드성능검증

Revision ID: 006
Revises: 005
Create Date: 2026-06-11

_category_definitions.py 에 추가된 3개 카테고리를 categories 테이블에 시드.
기존 6개(코딩컨벤션, 아키텍처, 온보딩, 보안, 배포, 기타)는 002 마이그레이션에서 추가됨.
ON CONFLICT DO NOTHING 으로 재실행 안전.
"""

from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO categories (name, description) VALUES
        ('AI_ML',      '인공지능, 머신러닝, 딥러닝, LLM, RAG, 임베딩, 벡터검색, MLOps, 모델 학습·배포·모니터링, 생성형 AI, 프롬프트 엔지니어링'),
        ('프로젝트관리', '프로젝트 관리, 스프린트, 회고, KPT, 일정, 이슈 관리, 애자일, 스크럼, 마일스톤, 팀 협업, 의사결정'),
        ('코드성능검증', '성능 테스트, 부하 테스트, 코드 최적화, 쿼리 성능, 응답 시간 측정, 병목 분석, 벤치마크, 캐시 전략')
        ON CONFLICT (name) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM categories
        WHERE name IN ('AI_ML', '프로젝트관리', '코드성능검증')
    """)
