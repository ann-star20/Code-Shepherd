"""TDD — categories DB 테이블 및 동적 카테고리 조회 테스트."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

class _FakeRow(dict):
    """asyncpg Record 처럼 dict 인덱스 접근을 지원하는 fake row."""
    pass


def _make_pool(rows: list[dict]):
    """asyncpg Pool mock — fetch 결과를 반환한다."""
    class _Conn:
        async def fetch(self, query, *args, **_kw):
            return [_FakeRow(row) for row in rows]

        async def execute(self, query, *args, **_kw):
            return "INSERT 1"

        async def fetchval(self, query, *args, **_kw):
            return rows[0].get("id", 1) if rows else None

    class _Ctx:
        async def __aenter__(self): return _Conn()
        async def __aexit__(self, *_): pass

    class _Pool:
        def acquire(self): return _Ctx()

    return _Pool()


# ---------------------------------------------------------------------------
# T3: categories 테이블 동적 조회
# ---------------------------------------------------------------------------

class TestCategoriesTable:
    """categories DB 테이블 CRUD 함수."""

    async def test_get_categories_returns_list(self):
        """get_categories()가 카테고리 이름 목록을 반환해야 한다."""
        from module_0_kms.categories_db import get_categories

        rows = [
            {"name": "코딩컨벤션", "description": "코딩 스타일"},
            {"name": "아키텍처",   "description": "SW 설계"},
        ]
        result = await get_categories(_make_pool(rows))
        assert isinstance(result, list)
        assert "코딩컨벤션" in result
        assert "아키텍처" in result

    async def test_get_categories_returns_only_names(self):
        """get_categories()는 name 필드만 추출해 반환한다."""
        from module_0_kms.categories_db import get_categories

        rows = [{"name": "보안", "description": "보안 정책", "active": True}]
        result = await get_categories(_make_pool(rows))
        assert result == ["보안"]
        assert all(isinstance(r, str) for r in result)

    async def test_add_category_inserts_row(self):
        """add_category()가 categories 테이블에 INSERT를 수행해야 한다."""
        from module_0_kms.categories_db import add_category

        executed = []

        class _Conn:
            async def execute(self, query, *args, **_kw):
                executed.append(query)

            async def fetchval(self, query, *args, **_kw):
                return 1

        class _Ctx:
            async def __aenter__(self): return _Conn()
            async def __aexit__(self, *_): pass

        class _Pool:
            def acquire(self): return _Ctx()

        await add_category(_Pool(), "NCS교육", "NCS 기반 교육 커리큘럼")
        assert any("INSERT" in q.upper() or "insert" in q for q in executed), (
            f"add_category가 INSERT를 수행하지 않음. 실행된 쿼리: {executed}"
        )

    async def test_add_category_deduplicates(self):
        """이미 존재하는 카테고리를 추가할 때 오류 없이 처리해야 한다 (ON CONFLICT 처리)."""
        from module_0_kms.categories_db import add_category

        class _Conn:
            async def execute(self, query, *args, **_kw):
                pass  # ON CONFLICT DO NOTHING — 오류 없음

            async def fetchval(self, query, *args, **_kw):
                return 1

        class _Ctx:
            async def __aenter__(self): return _Conn()
            async def __aexit__(self, *_): pass

        class _Pool:
            def acquire(self): return _Ctx()

        # 동일한 카테고리를 두 번 추가해도 예외 없음
        await add_category(_Pool(), "아키텍처", "")
        await add_category(_Pool(), "아키텍처", "")

    async def test_get_valid_categories_frozenset(self):
        """get_valid_categories()가 frozenset을 반환해야 한다."""
        from module_0_kms.categories_db import get_valid_categories

        rows = [{"name": "코딩컨벤션"}, {"name": "아키텍처"}]
        result = await get_valid_categories(_make_pool(rows))
        assert isinstance(result, frozenset)
        assert "코딩컨벤션" in result
