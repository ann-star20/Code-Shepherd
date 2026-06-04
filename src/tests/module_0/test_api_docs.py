"""Tests for GET /kms/docs endpoint."""

from __future__ import annotations

import datetime

import pytest
from fastapi import HTTPException

import module_0_kms.api as api
from module_0_kms.api import list_documents


class _AcquireContext:
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
        return _AcquireContext(self._conn)


_NOW = datetime.datetime(2026, 5, 30, 12, 0, 0, tzinfo=datetime.timezone.utc)


def _doc_row(
    doc_id: str = "00000000-0000-0000-0000-000000000001",
    title: str = "테스트 문서",
    file_type: str = "pdf",
    status: str = "stored",
) -> dict:
    return {
        "doc_id": doc_id,
        "title": title,
        "file_type": file_type,
        "upload_status": status,
        "created_at": _NOW,
    }


# ---------------------------------------------------------------------------
# 기본 목록 조회
# ---------------------------------------------------------------------------

class TestListDocumentsBasic:
    async def test_returns_list_of_docs(self, monkeypatch):
        """문서가 2개 있을 때 2개가 반환된다."""
        rows = [
            _doc_row("00000000-0000-0000-0000-000000000001", status="stored"),
            _doc_row("00000000-0000-0000-0000-000000000002", status="processing"),
        ]

        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return {"count": len(rows)}

            async def fetch(self, *_a, **_kw):
                return rows

        monkeypatch.setattr(api, "_db_pool", _FakePool(Conn()))
        result = await list_documents()
        assert len(result.docs) == 2

    async def test_doc_fields_present(self, monkeypatch):
        """각 doc 항목에 필수 필드가 포함된다."""
        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return {"count": 1}

            async def fetch(self, *_a, **_kw):
                return [_doc_row()]

        monkeypatch.setattr(api, "_db_pool", _FakePool(Conn()))
        result = await list_documents()
        doc = result.docs[0]
        assert doc.doc_id is not None
        assert doc.title == "테스트 문서"
        assert doc.file_type == "pdf"
        assert doc.status == "stored"
        assert doc.created_at is not None

    async def test_empty_list_when_no_docs(self, monkeypatch):
        """문서가 없으면 빈 리스트를 반환한다."""
        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return {"count": 0}

            async def fetch(self, *_a, **_kw):
                return []

        monkeypatch.setattr(api, "_db_pool", _FakePool(Conn()))
        result = await list_documents()
        assert result.docs == []
        assert result.total == 0

    async def test_total_reflects_count_query(self, monkeypatch):
        """total은 실제 필터된 전체 건수(COUNT)를 반영한다."""
        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return {"count": 42}

            async def fetch(self, *_a, **_kw):
                return [_doc_row()]

        monkeypatch.setattr(api, "_db_pool", _FakePool(Conn()))
        result = await list_documents(limit=1)
        assert result.total == 42


# ---------------------------------------------------------------------------
# status 필터
# ---------------------------------------------------------------------------

class TestListDocumentsStatusFilter:
    async def test_status_filter_passed_to_query(self, monkeypatch):
        """status 파라미터를 전달하면 해당 상태 문서만 반환된다."""
        captured = {}

        class Conn:
            async def fetchrow(self, query, *args, **_kw):
                captured["count_args"] = args
                return {"count": 1}

            async def fetch(self, query, *args, **_kw):
                captured["fetch_query"] = query
                captured["fetch_args"] = args
                return [_doc_row(status="stored")]

        monkeypatch.setattr(api, "_db_pool", _FakePool(Conn()))
        result = await list_documents(status="stored")
        assert result.docs[0].status == "stored"
        # status 값이 쿼리 인자로 전달됐는지 확인
        assert "stored" in captured.get("fetch_args", ())

    async def test_no_status_filter_returns_all(self, monkeypatch):
        """status 파라미터 없으면 전체 상태 문서를 반환한다."""
        rows = [
            _doc_row(status="stored"),
            _doc_row(status="processing"),
            _doc_row(status="failed"),
        ]

        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return {"count": len(rows)}

            async def fetch(self, *_a, **_kw):
                return rows

        monkeypatch.setattr(api, "_db_pool", _FakePool(Conn()))
        result = await list_documents()
        assert len(result.docs) == 3

    async def test_invalid_status_raises_422(self, monkeypatch):
        """허용되지 않은 status 값은 422를 반환한다."""
        monkeypatch.setattr(api, "_db_pool", _FakePool(None))
        with pytest.raises(HTTPException) as exc_info:
            await list_documents(status="invalid_status_xyz")
        assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# 페이지네이션
# ---------------------------------------------------------------------------

class TestListDocumentsPagination:
    async def test_default_limit_is_20(self, monkeypatch):
        """기본 limit은 20이다."""
        captured = {}

        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return {"count": 0}

            async def fetch(self, query, *args, **_kw):
                captured["args"] = args
                return []

        monkeypatch.setattr(api, "_db_pool", _FakePool(Conn()))
        await list_documents()
        assert 20 in captured.get("args", ())

    async def test_custom_limit_applied(self, monkeypatch):
        """limit=5 이면 쿼리에 5가 전달된다."""
        captured = {}

        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return {"count": 0}

            async def fetch(self, query, *args, **_kw):
                captured["args"] = args
                return []

        monkeypatch.setattr(api, "_db_pool", _FakePool(Conn()))
        await list_documents(limit=5)
        assert 5 in captured.get("args", ())

    async def test_offset_applied(self, monkeypatch):
        """offset=10 이면 쿼리에 10이 전달된다."""
        captured = {}

        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return {"count": 0}

            async def fetch(self, query, *args, **_kw):
                captured["args"] = args
                return []

        monkeypatch.setattr(api, "_db_pool", _FakePool(Conn()))
        await list_documents(offset=10)
        assert 10 in captured.get("args", ())

    async def test_limit_exceeding_100_raises_422(self, monkeypatch):
        """limit이 100을 초과하면 422를 반환한다."""
        monkeypatch.setattr(api, "_db_pool", _FakePool(None))
        with pytest.raises(HTTPException) as exc_info:
            await list_documents(limit=101)
        assert exc_info.value.status_code == 422

    async def test_limit_zero_raises_422(self, monkeypatch):
        """limit=0은 422를 반환한다."""
        monkeypatch.setattr(api, "_db_pool", _FakePool(None))
        with pytest.raises(HTTPException) as exc_info:
            await list_documents(limit=0)
        assert exc_info.value.status_code == 422

    async def test_negative_offset_raises_422(self, monkeypatch):
        """음수 offset은 422를 반환한다."""
        monkeypatch.setattr(api, "_db_pool", _FakePool(None))
        with pytest.raises(HTTPException) as exc_info:
            await list_documents(offset=-1)
        assert exc_info.value.status_code == 422

    async def test_response_includes_limit_and_offset(self, monkeypatch):
        """응답에 limit과 offset이 포함된다."""
        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return {"count": 0}

            async def fetch(self, *_a, **_kw):
                return []

        monkeypatch.setattr(api, "_db_pool", _FakePool(Conn()))
        result = await list_documents(limit=10, offset=5)
        assert result.limit == 10
        assert result.offset == 5


# ---------------------------------------------------------------------------
# null 필드 처리
# ---------------------------------------------------------------------------

class TestListDocumentsNullFields:
    async def test_null_title_allowed(self, monkeypatch):
        """title이 NULL인 문서도 정상 반환된다."""
        row = {**_doc_row(), "title": None}

        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return {"count": 1}

            async def fetch(self, *_a, **_kw):
                return [row]

        monkeypatch.setattr(api, "_db_pool", _FakePool(Conn()))
        result = await list_documents()
        assert result.docs[0].title is None

    async def test_null_created_at_allowed(self, monkeypatch):
        """created_at이 NULL인 문서도 정상 반환된다."""
        row = {**_doc_row(), "created_at": None}

        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return {"count": 1}

            async def fetch(self, *_a, **_kw):
                return [row]

        monkeypatch.setattr(api, "_db_pool", _FakePool(Conn()))
        result = await list_documents()
        assert result.docs[0].created_at is None
