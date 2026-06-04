"""Tests for GET /kms/docs/{doc_id}/metadata endpoint."""

from __future__ import annotations

import datetime

import pytest

import module_0_kms.api as api
from module_0_kms.api import get_doc_metadata


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


_NOW = datetime.datetime(2026, 5, 30, tzinfo=datetime.timezone.utc)
_DOC_ID = "00000000-0000-0000-0000-000000000099"


def _doc_row(
    title: str = "N+1 쿼리 방지 가이드",
    category: str = "코딩컨벤션",
    source: str = "upload",
    file_type: str = "pdf",
    created_at=_NOW,
) -> dict:
    return {
        "title": title,
        "category": category,
        "source": source,
        "file_type": file_type,
        "created_at": created_at,
    }


def _meta_row(team: str | None = "백엔드팀", tags: list | None = None) -> dict:
    return {
        "metadata": {
            "category": "코딩컨벤션",
            "team": team,
            "tags": tags if tags is not None else ["N+1", "ORM", "쿼리"],
            "section_header": None,
        }
    }


class _ConnTwoFetch:
    """두 번의 fetchrow를 순서대로 반환한다."""

    def __init__(self, doc_row: dict | None, meta_row: dict | None):
        self._doc_row = doc_row
        self._meta_row = meta_row
        self._call_count = 0

    async def fetchrow(self, query: str, *_args, **_kw):
        self._call_count += 1
        if "documents" in query:
            return self._doc_row
        return self._meta_row


# ---------------------------------------------------------------------------
# 유효하지 않은 UUID
# ---------------------------------------------------------------------------

class TestDocMetadataInvalidUUID:
    async def test_invalid_uuid_raises_422(self, monkeypatch):
        from fastapi import HTTPException
        monkeypatch.setattr(api, "_db_pool", _FakePool(None))

        with pytest.raises(HTTPException) as exc_info:
            await get_doc_metadata("not-a-uuid")
        assert exc_info.value.status_code == 422

    async def test_partial_uuid_raises_422(self, monkeypatch):
        from fastapi import HTTPException
        monkeypatch.setattr(api, "_db_pool", _FakePool(None))

        with pytest.raises(HTTPException) as exc_info:
            await get_doc_metadata("12345678-bad")
        assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# 문서 미존재
# ---------------------------------------------------------------------------

class TestDocMetadataNotFound:
    async def test_missing_doc_raises_404(self, monkeypatch):
        from fastapi import HTTPException

        conn = _ConnTwoFetch(doc_row=None, meta_row=None)
        monkeypatch.setattr(api, "_db_pool", _FakePool(conn))

        with pytest.raises(HTTPException) as exc_info:
            await get_doc_metadata(_DOC_ID)
        assert exc_info.value.status_code == 404
        assert _DOC_ID in exc_info.value.detail


# ---------------------------------------------------------------------------
# documents 테이블 기본 필드 반환
# ---------------------------------------------------------------------------

class TestDocMetadataBasicFields:
    async def test_doc_id_in_response(self, monkeypatch):
        """응답에 요청한 doc_id가 포함된다."""
        conn = _ConnTwoFetch(_doc_row(), _meta_row())
        monkeypatch.setattr(api, "_db_pool", _FakePool(conn))
        result = await get_doc_metadata(_DOC_ID)
        assert result.doc_id == _DOC_ID

    async def test_title_returned(self, monkeypatch):
        """documents.title이 응답에 포함된다."""
        conn = _ConnTwoFetch(_doc_row(title="SQL 인젝션 방지"), _meta_row())
        monkeypatch.setattr(api, "_db_pool", _FakePool(conn))
        result = await get_doc_metadata(_DOC_ID)
        assert result.title == "SQL 인젝션 방지"

    async def test_category_returned(self, monkeypatch):
        """documents.category가 응답에 포함된다."""
        conn = _ConnTwoFetch(_doc_row(category="보안"), _meta_row())
        monkeypatch.setattr(api, "_db_pool", _FakePool(conn))
        result = await get_doc_metadata(_DOC_ID)
        assert result.category == "보안"

    async def test_source_returned(self, monkeypatch):
        """documents.source가 응답에 포함된다."""
        conn = _ConnTwoFetch(_doc_row(source="notion"), _meta_row())
        monkeypatch.setattr(api, "_db_pool", _FakePool(conn))
        result = await get_doc_metadata(_DOC_ID)
        assert result.source == "notion"

    async def test_file_type_returned(self, monkeypatch):
        """documents.file_type이 응답에 포함된다."""
        conn = _ConnTwoFetch(_doc_row(file_type="docx"), _meta_row())
        monkeypatch.setattr(api, "_db_pool", _FakePool(conn))
        result = await get_doc_metadata(_DOC_ID)
        assert result.file_type == "docx"

    async def test_created_at_returned(self, monkeypatch):
        """documents.created_at이 ISO8601 문자열로 반환된다."""
        conn = _ConnTwoFetch(_doc_row(), _meta_row())
        monkeypatch.setattr(api, "_db_pool", _FakePool(conn))
        result = await get_doc_metadata(_DOC_ID)
        assert result.created_at == _NOW.isoformat()

    async def test_null_created_at_allowed(self, monkeypatch):
        """created_at이 NULL이어도 오류 없이 반환된다."""
        conn = _ConnTwoFetch(_doc_row(created_at=None), _meta_row())
        monkeypatch.setattr(api, "_db_pool", _FakePool(conn))
        result = await get_doc_metadata(_DOC_ID)
        assert result.created_at is None


# ---------------------------------------------------------------------------
# chunk_embeddings.metadata 에서 team / tags 반환
# ---------------------------------------------------------------------------

class TestDocMetadataTeamTags:
    async def test_team_from_chunk_embeddings(self, monkeypatch):
        """chunk_embeddings.metadata.team이 응답에 포함된다."""
        conn = _ConnTwoFetch(_doc_row(), _meta_row(team="인프라팀"))
        monkeypatch.setattr(api, "_db_pool", _FakePool(conn))
        result = await get_doc_metadata(_DOC_ID)
        assert result.team == "인프라팀"

    async def test_tags_from_chunk_embeddings(self, monkeypatch):
        """chunk_embeddings.metadata.tags 리스트가 응답에 포함된다."""
        conn = _ConnTwoFetch(_doc_row(), _meta_row(tags=["FastAPI", "PostgreSQL"]))
        monkeypatch.setattr(api, "_db_pool", _FakePool(conn))
        result = await get_doc_metadata(_DOC_ID)
        assert result.tags == ["FastAPI", "PostgreSQL"]

    async def test_null_team_returned_as_none(self, monkeypatch):
        """chunk_embeddings.metadata.team이 NULL이면 None을 반환한다."""
        conn = _ConnTwoFetch(_doc_row(), _meta_row(team=None))
        monkeypatch.setattr(api, "_db_pool", _FakePool(conn))
        result = await get_doc_metadata(_DOC_ID)
        assert result.team is None


# ---------------------------------------------------------------------------
# chunk_embeddings 없을 때 (임베딩이 아직 생성되지 않은 문서)
# ---------------------------------------------------------------------------

class TestDocMetadataNoChunks:
    async def test_no_chunk_embeddings_returns_empty_tags(self, monkeypatch):
        """chunk_embeddings 없으면 tags는 빈 리스트를 반환한다."""
        conn = _ConnTwoFetch(_doc_row(), meta_row=None)
        monkeypatch.setattr(api, "_db_pool", _FakePool(conn))
        result = await get_doc_metadata(_DOC_ID)
        assert result.tags == []

    async def test_no_chunk_embeddings_team_is_none(self, monkeypatch):
        """chunk_embeddings 없으면 team은 None을 반환한다."""
        conn = _ConnTwoFetch(_doc_row(), meta_row=None)
        monkeypatch.setattr(api, "_db_pool", _FakePool(conn))
        result = await get_doc_metadata(_DOC_ID)
        assert result.team is None
