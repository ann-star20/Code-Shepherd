"""TDD (RED): search_kms category 필터 — asyncpg AmbiguousParameterError 재현 및 수정 검증.

버그: category=None 시 asyncpg가 untyped NULL 전송 → PostgreSQL 파싱 단계 실패
    asyncpg.exceptions.AmbiguousParameterError: could not determine data type of parameter $2

수정 방향:
    1. category 입력 정규화: None / "" / 공백 → None
    2. sqlalchemy bindparam(type_=String) 으로 타입 명시

테스트 대상:
    app.routes.kms_routes._normalize_category   (순수 함수, DB 불필요)
    app.routes.kms_routes.build_search_params    (SQL 파라미터 딕셔너리 생성)
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import String
from sqlalchemy import bindparam as sa_bindparam


# ---------------------------------------------------------------------------
# User Journey 1: category 정규화
# ---------------------------------------------------------------------------

class TestNormalizeCategory:

    def test_none_returns_none(self):
        """category=None 은 None을 반환해야 한다."""
        from app.routes.kms_routes import _normalize_category

        assert _normalize_category(None) is None

    def test_empty_string_returns_none(self):
        """category='' 은 None으로 정규화되어야 한다."""
        from app.routes.kms_routes import _normalize_category

        assert _normalize_category("") is None

    def test_whitespace_only_returns_none(self):
        """category='   ' 는 None으로 정규화되어야 한다."""
        from app.routes.kms_routes import _normalize_category

        assert _normalize_category("   ") is None

    def test_valid_category_returned_as_is(self):
        """유효한 카테고리 문자열은 그대로 반환되어야 한다."""
        from app.routes.kms_routes import _normalize_category

        assert _normalize_category("보안") == "보안"

    def test_category_with_whitespace_preserved(self):
        """앞뒤 공백이 있는 유효 카테고리는 strip 후 반환되어야 한다."""
        from app.routes.kms_routes import _normalize_category

        assert _normalize_category("  보안  ") == "보안"


# ---------------------------------------------------------------------------
# User Journey 2: SQL 파라미터에 category bindparam 타입이 명시되어야 한다
# ---------------------------------------------------------------------------

class TestSearchQueryBindparam:

    def test_search_sql_text_has_category_bindparam_with_type(self):
        """search SQL TextClause에 category bindparam이 String 타입으로 등록되어야 한다."""
        from app.routes.kms_routes import _build_search_sql

        sql_clause = _build_search_sql()
        # bindparams에 'category'가 String 타입으로 설정되어 있어야 함
        bound = {p.key: p for p in sql_clause._bindparams.values()}
        assert "category" in bound, (
            "_build_search_sql()가 반환하는 TextClause에 'category' bindparam이 없습니다."
        )
        assert isinstance(bound["category"].type, String), (
            "category bindparam의 type이 String이 아닙니다. "
            "asyncpg가 untyped NULL을 전송하면 PostgreSQL이 타입 추론에 실패합니다."
        )

    def test_search_sql_text_contains_category_is_null_pattern(self):
        """SQL에 category IS NULL OR = :category 패턴이 있어야 한다."""
        from app.routes.kms_routes import _build_search_sql

        sql_str = _build_search_sql().text
        assert "category" in sql_str.lower()
        assert "IS NULL" in sql_str or "is null" in sql_str.lower()


# ---------------------------------------------------------------------------
# User Journey 3: category=None 시 500 에러 없이 정상 동작
# ---------------------------------------------------------------------------

class TestSearchKmsCategoryNone:

    @pytest.mark.asyncio
    async def test_search_without_category_does_not_raise(self):
        """category=None 으로 검색 시 AmbiguousParameterError가 발생하지 않아야 한다."""
        # 실제 DB 없이, session.execute가 호출되는지만 확인
        mock_rows = MagicMock()
        mock_rows.mappings.return_value.fetchall.return_value = []

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_rows
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_factory = MagicMock(return_value=mock_session)

        fake_embedding = [0.1] * 1024

        with (
            patch("app.routes.kms_routes._embed_query", return_value=fake_embedding),
            patch("app.routes.kms_routes._get_session_factory", return_value=mock_factory),
        ):
            from app.routes.kms_routes import search_kms

            current_user = {"team": "engineering", "user_id": "user-123"}
            result = await search_kms(
                q="보안 정책",
                limit=5,
                category=None,
                current_user=current_user,
            )

        # session.execute가 호출되었어야 함 (파싱 단계 에러 없이)
        mock_session.execute.assert_called_once()
        assert result is not None

    @pytest.mark.asyncio
    async def test_search_with_empty_string_category_treated_as_none(self):
        """category='' 은 None으로 정규화되어 정상 동작해야 한다."""
        mock_rows = MagicMock()
        mock_rows.mappings.return_value.fetchall.return_value = []

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_rows
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_factory = MagicMock(return_value=mock_session)

        fake_embedding = [0.1] * 1024

        with (
            patch("app.routes.kms_routes._embed_query", return_value=fake_embedding),
            patch("app.routes.kms_routes._get_session_factory", return_value=mock_factory),
        ):
            from app.routes.kms_routes import search_kms

            current_user = {"team": "engineering", "user_id": "user-123"}
            result = await search_kms(
                q="보안 정책",
                limit=5,
                category="",
                current_user=current_user,
            )

        mock_session.execute.assert_called_once()
        # 호출 시 전달된 파라미터에서 category 확인
        call_args = mock_session.execute.call_args
        params = call_args[0][1] if call_args[0] else call_args[1].get("parameters", {})
        assert params.get("category") is None, (
            f"category='' 이 None으로 정규화되지 않았습니다. 실제값: {params.get('category')}"
        )

    @pytest.mark.asyncio
    async def test_search_with_valid_category_passes_through(self):
        """category='보안' 은 그대로 SQL에 전달되어야 한다."""
        mock_rows = MagicMock()
        mock_rows.mappings.return_value.fetchall.return_value = []

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_rows
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_factory = MagicMock(return_value=mock_session)

        fake_embedding = [0.1] * 1024

        with (
            patch("app.routes.kms_routes._embed_query", return_value=fake_embedding),
            patch("app.routes.kms_routes._get_session_factory", return_value=mock_factory),
        ):
            from app.routes.kms_routes import search_kms

            current_user = {"team": "engineering", "user_id": "user-123"}
            result = await search_kms(
                q="보안 정책",
                limit=5,
                category="보안",
                current_user=current_user,
            )

        mock_session.execute.assert_called_once()
        call_args = mock_session.execute.call_args
        params = call_args[0][1] if call_args[0] else call_args[1].get("parameters", {})
        assert params.get("category") == "보안"
