"""
TDD Cycle 6: stage6_store — metadata_score DB 저장

문제:
  - DocPipelineState.metadata_score (Stage 5b 출력)가 documents 테이블에 저장되지 않음
  - _save_document() INSERT에 metadata_score 파라미터 없음
  - Document ORM 모델에 metadata_score 컬럼 없음

목표:
  - _save_document() SQL에 metadata_score 포함
  - Document ORM 모델에 metadata_score: Float, nullable=True 추가
  - Alembic 마이그레이션 009 생성
"""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock, call


DOC_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _make_base_state(metadata_score: float | None = None) -> dict:
    return {
        "doc_id": DOC_ID,
        "source": "upload",
        "file_type": "md",
        "file_path": "",
        "original_filename": "test.md",
        "metadata": {"title": "테스트", "category": "AI_ML"},
        "quality_score": 0.9,
        "metadata_score": metadata_score,
        "parser_used": "direct_read",
        "doc_complexity": "LOW",
        "parsing_time_ms": 1000,
        "department_id": None,
        "user_id": None,
        "permission_level": "public",
        "visibility": "all",
        "file_hash": None,
    }


def _make_mock_session() -> tuple[AsyncMock, list[dict]]:
    """AsyncSession mock과 실행된 파라미터를 수집하는 리스트를 반환한다."""
    captured: list[dict] = []
    session = AsyncMock()

    async def mock_execute(query, params=None):
        if isinstance(params, dict):
            captured.append(dict(params))
        elif isinstance(params, list) and params:
            captured.extend(params)
        return MagicMock()

    session.execute = mock_execute
    return session, captured


class TestSaveDocumentMetadataScore:
    """`_save_document()` 함수가 metadata_score를 SQL 파라미터에 포함하는지 검증."""

    async def test_metadata_score_in_sql_params(self):
        """state['metadata_score'] = 0.85 → SQL 파라미터에 metadata_score = 0.85 포함."""
        from app.pipeline.stage6_store import _save_document

        session, captured = _make_mock_session()
        state = _make_base_state(metadata_score=0.85)

        await _save_document(session, state, "markdown/path.md", "original/path.md")

        assert captured, "_save_document()가 session.execute를 호출하지 않음"
        params = captured[0]
        assert "metadata_score" in params, (
            f"SQL 파라미터에 'metadata_score'가 없음. 실제 키: {list(params.keys())}"
        )
        assert params["metadata_score"] == pytest.approx(0.85)

    async def test_none_metadata_score_passed_as_null(self):
        """state에 metadata_score가 없으면 NULL (None)로 저장해야 한다."""
        from app.pipeline.stage6_store import _save_document

        session, captured = _make_mock_session()
        state = _make_base_state(metadata_score=None)
        # state에서 metadata_score 키를 아예 제거
        del state["metadata_score"]

        await _save_document(session, state, "markdown/path.md", "original/path.md")

        params = captured[0]
        assert "metadata_score" in params
        assert params["metadata_score"] is None

    async def test_zero_metadata_score_preserved(self):
        """metadata_score = 0.0도 None이 아니라 0.0으로 저장되어야 한다."""
        from app.pipeline.stage6_store import _save_document

        session, captured = _make_mock_session()
        state = _make_base_state(metadata_score=0.0)

        await _save_document(session, state, "markdown/path.md", "original/path.md")

        params = captured[0]
        assert params["metadata_score"] == pytest.approx(0.0)


class TestDocumentOrmHasMetadataScore:
    """Document ORM 모델에 metadata_score 컬럼이 있는지 검증."""

    def test_document_orm_has_metadata_score_attribute(self):
        """Document 클래스가 metadata_score 속성을 가져야 한다."""
        from app.models import Document

        assert hasattr(Document, "metadata_score"), (
            "Document ORM 모델에 'metadata_score' 컬럼이 없음 — app/models.py 수정 필요"
        )

    def test_document_orm_metadata_score_is_nullable(self):
        """metadata_score 컬럼은 nullable=True여야 한다 (기존 문서 호환성)."""
        from app.models import Document
        import sqlalchemy as sa

        col = Document.__table__.c.get("metadata_score")
        assert col is not None, "metadata_score 컬럼을 테이블에서 찾을 수 없음"
        assert col.nullable is True, f"metadata_score.nullable = {col.nullable} (True여야 함)"


class TestAlembicMigration009:
    """Alembic 마이그레이션 009이 존재하고 metadata_score를 추가하는지 검증."""

    def test_migration_file_exists(self):
        """009_add_metadata_score_to_documents.py 파일이 존재해야 한다."""
        from pathlib import Path
        migration_path = Path(__file__).parent.parent / "alembic" / "versions" / "009_add_metadata_score_to_documents.py"
        assert migration_path.exists(), (
            f"마이그레이션 파일 없음: {migration_path}\n"
            "Alembic 마이그레이션 009을 생성해야 함"
        )

    def test_migration_adds_metadata_score_column(self):
        """마이그레이션이 'metadata_score' 컬럼을 추가하는 내용을 포함해야 한다."""
        from pathlib import Path
        migration_path = Path(__file__).parent.parent / "alembic" / "versions" / "009_add_metadata_score_to_documents.py"
        if not migration_path.exists():
            return  # 위 테스트에서 이미 실패
        content = migration_path.read_text(encoding="utf-8")
        assert "metadata_score" in content, "마이그레이션 파일에 'metadata_score' 없음"


import pytest
