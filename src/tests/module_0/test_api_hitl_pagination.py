"""Tests for GET /hitl/queue pagination (limit / offset).

TDD RED → GREEN:
  현재 list_hitl_queue는 limit/offset 파라미터가 없고 list[HitlQueueItem]을 반환한다.
  목표: HitlQueuePageResponse(items, total, limit, offset) 반환 + LIMIT/OFFSET SQL 전달.
"""

from __future__ import annotations

import pytest

import module_0_kms.hitl_api as hitl_api
from module_0_kms.hitl_api import list_hitl_queue


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------


class _AcquireCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *_):
        return False


class _FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _AcquireCtx(self._conn)


def _queue_row(status: str = "pending") -> dict:
    return {
        "queue_id": "11111111-1111-1111-1111-111111111111",
        "doc_id": "22222222-2222-2222-2222-222222222222",
        "stage": "stage2_validate",
        "reason": "품질 기준 미달",
        "quality_score": 0.5,
        "issues": None,
        "status": status,
        "reviewer_id": None,
        "review_note": None,
        "created_at": "2026-05-25T00:00:00+00:00",
    }


class _ConnPagination:
    """COUNT fetchrow + 페이지 fetch 를 모두 지원하는 커넥션 Mock."""

    def __init__(self, total: int = 0, rows: list | None = None):
        self._total = total
        self._rows = rows if rows is not None else []
        self.last_fetch_args: tuple | None = None

    async def fetchrow(self, query: str, *_args, **_kw):
        return {"total": self._total}

    async def fetch(self, query: str, *args, **_kw):
        self.last_fetch_args = args
        return self._rows


# ---------------------------------------------------------------------------
# 응답 필드 구조
# ---------------------------------------------------------------------------


class TestHitlQueuePaginationFields:
    async def test_response_has_items_field(self, monkeypatch):
        """응답에 items 필드가 포함된다."""
        conn = _ConnPagination(total=1, rows=[_queue_row()])
        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(conn))
        result = await list_hitl_queue(status="pending")
        assert hasattr(result, "items")

    async def test_response_has_total_field(self, monkeypatch):
        """응답에 total 필드가 포함된다."""
        conn = _ConnPagination(total=5)
        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(conn))
        result = await list_hitl_queue(status="pending")
        assert hasattr(result, "total")

    async def test_response_has_limit_field(self, monkeypatch):
        """응답에 limit 필드가 포함된다."""
        conn = _ConnPagination(total=0, rows=[])
        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(conn))
        result = await list_hitl_queue(status="pending")
        assert hasattr(result, "limit")

    async def test_response_has_offset_field(self, monkeypatch):
        """응답에 offset 필드가 포함된다."""
        conn = _ConnPagination(total=0, rows=[])
        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(conn))
        result = await list_hitl_queue(status="pending")
        assert hasattr(result, "offset")


# ---------------------------------------------------------------------------
# 응답 값 검증
# ---------------------------------------------------------------------------


class TestHitlQueuePaginationValues:
    async def test_default_limit_is_20(self, monkeypatch):
        """파라미터 없을 때 기본 limit은 20이다."""
        conn = _ConnPagination(total=0, rows=[])
        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(conn))
        result = await list_hitl_queue(status="pending")
        assert result.limit == 20

    async def test_custom_limit_reflected_in_response(self, monkeypatch):
        """limit=5이면 response.limit == 5이다."""
        conn = _ConnPagination(total=0, rows=[])
        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(conn))
        result = await list_hitl_queue(status="pending", limit=5)
        assert result.limit == 5

    async def test_custom_offset_reflected_in_response(self, monkeypatch):
        """offset=10이면 response.offset == 10이다."""
        conn = _ConnPagination(total=0, rows=[])
        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(conn))
        result = await list_hitl_queue(status="pending", offset=10)
        assert result.offset == 10

    async def test_total_reflects_count_query(self, monkeypatch):
        """total은 COUNT(*) 쿼리 결과와 일치한다."""
        conn = _ConnPagination(total=42, rows=[])
        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(conn))
        result = await list_hitl_queue(status="pending")
        assert result.total == 42

    async def test_empty_items_when_no_rows(self, monkeypatch):
        """행이 없으면 items는 빈 리스트이다."""
        conn = _ConnPagination(total=0, rows=[])
        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(conn))
        result = await list_hitl_queue(status="pending")
        assert result.items == []

    async def test_items_contains_hitl_queue_items(self, monkeypatch):
        """items 목록 각 항목은 HitlQueueItem 타입이다."""
        from module_0_kms.hitl_api import HitlQueueItem

        conn = _ConnPagination(total=1, rows=[_queue_row()])
        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(conn))
        result = await list_hitl_queue(status="pending")
        assert len(result.items) == 1
        assert isinstance(result.items[0], HitlQueueItem)


# ---------------------------------------------------------------------------
# DB 쿼리 인자 검증 (limit / offset이 SQL에 전달되는지)
# ---------------------------------------------------------------------------


class TestHitlQueuePaginationDbArgs:
    async def test_limit_passed_to_db_query(self, monkeypatch):
        """limit 파라미터가 DB fetch 쿼리 인자로 전달된다."""
        conn = _ConnPagination(total=0, rows=[])
        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(conn))
        await list_hitl_queue(status="pending", limit=7)
        assert conn.last_fetch_args is not None
        assert 7 in conn.last_fetch_args

    async def test_offset_passed_to_db_query(self, monkeypatch):
        """offset 파라미터가 DB fetch 쿼리 인자로 전달된다."""
        conn = _ConnPagination(total=0, rows=[])
        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(conn))
        await list_hitl_queue(status="pending", offset=15)
        assert conn.last_fetch_args is not None
        assert 15 in conn.last_fetch_args
