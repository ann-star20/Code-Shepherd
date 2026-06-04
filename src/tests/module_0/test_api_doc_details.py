"""Tests for GET /kms/docs/{doc_id}/details endpoint."""

from __future__ import annotations

import datetime
from uuid import UUID

import pytest

import module_0_kms.api as api
from module_0_kms.api import get_doc_details


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


def _fake_doc_row(status: str = "stored") -> dict:
    return {
        "title": "테스트 문서",
        "file_type": "md",
        "upload_status": status,
        "created_at": datetime.datetime(2026, 5, 25, tzinfo=datetime.timezone.utc),
        "parser_used": None,
        "quality_score": None,
        "doc_complexity": None,
        "parsing_time_ms": None,
    }


def _fake_trace_row() -> dict:
    now = datetime.datetime(2026, 5, 25, 10, 0, 0, tzinfo=datetime.timezone.utc)
    return {
        "trace_id": "trc_0001_abcd1234",
        "agent_name": "DocumentParserAgent",
        "status": "success",
        "started_at": now,
        "ended_at": now,
        "execution_ms": 50,
        "error_message": None,
    }


def _fake_chunk_row() -> dict:
    return {
        "chunk_id": "chunk-uuid-001",
        "chunk_type": "parent",
        "content": "# 제목\n\n내용",
        "token_count": 150,
        "section_header": "제목",
        "page_number": None,
    }


# ---------------------------------------------------------------------------
# 유효하지 않은 UUID
# ---------------------------------------------------------------------------

class TestInvalidDocId:
    async def test_invalid_uuid_raises_422(self, monkeypatch):
        from fastapi import HTTPException
        monkeypatch.setattr(api, "_db_pool", _FakePool(None))

        with pytest.raises(HTTPException) as exc_info:
            await get_doc_details("not-a-uuid")
        assert exc_info.value.status_code == 422

    async def test_partial_uuid_raises_422(self, monkeypatch):
        from fastapi import HTTPException
        monkeypatch.setattr(api, "_db_pool", _FakePool(None))

        with pytest.raises(HTTPException) as exc_info:
            await get_doc_details("12345678-wrong")
        assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# 문서 미존재
# ---------------------------------------------------------------------------

class TestDocNotFound:
    async def test_missing_doc_raises_404(self, monkeypatch):
        from fastapi import HTTPException

        class Conn:
            async def fetchrow(self, *_args, **_kw):
                return None  # 문서 없음

            async def fetch(self, *_args, **_kw):
                return []

        monkeypatch.setattr(api, "_db_pool", _FakePool(Conn()))
        doc_id = "00000000-0000-0000-0000-000000000000"

        with pytest.raises(HTTPException) as exc_info:
            await get_doc_details(doc_id)
        assert exc_info.value.status_code == 404
        assert doc_id in exc_info.value.detail


# ---------------------------------------------------------------------------
# 정상 응답
# ---------------------------------------------------------------------------

class TestDocDetailsSuccess:
    async def test_returns_correct_doc_id(self, monkeypatch):
        doc_id = "eab0aff1-16ee-4033-8fb2-caf8e6a43feb"

        class Conn:
            async def fetchrow(self, *_args, **_kw):
                return _fake_doc_row()

            async def fetch(self, query, *_args, **_kw):
                if "agent_traces" in query:
                    return [_fake_trace_row()]
                return [_fake_chunk_row()]

        monkeypatch.setattr(api, "_db_pool", _FakePool(Conn()))
        result = await get_doc_details(doc_id)
        assert result.doc_id == doc_id

    async def test_traces_deserialized_correctly(self, monkeypatch):
        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return _fake_doc_row()

            async def fetch(self, query, *_a, **_kw):
                if "agent_traces" in query:
                    return [_fake_trace_row()]
                return []

        monkeypatch.setattr(api, "_db_pool", _FakePool(Conn()))
        result = await get_doc_details("eab0aff1-16ee-4033-8fb2-caf8e6a43feb")
        assert len(result.agent_traces) == 1
        assert result.agent_traces[0].agent_name == "DocumentParserAgent"
        assert result.agent_traces[0].status == "success"
        assert result.agent_traces[0].execution_ms == 50

    async def test_chunks_deserialized_correctly(self, monkeypatch):
        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return _fake_doc_row()

            async def fetch(self, query, *_a, **_kw):
                if "agent_traces" in query:
                    return []
                return [_fake_chunk_row()]

        monkeypatch.setattr(api, "_db_pool", _FakePool(Conn()))
        result = await get_doc_details("eab0aff1-16ee-4033-8fb2-caf8e6a43feb")
        assert len(result.chunks) == 1
        assert result.chunks[0].chunk_type == "parent"
        assert result.chunks[0].token_count == 150

    async def test_empty_traces_and_chunks_allowed(self, monkeypatch):
        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return _fake_doc_row()

            async def fetch(self, *_a, **_kw):
                return []

        monkeypatch.setattr(api, "_db_pool", _FakePool(Conn()))
        result = await get_doc_details("eab0aff1-16ee-4033-8fb2-caf8e6a43feb")
        assert result.agent_traces == []
        assert result.chunks == []

    async def test_title_and_status_from_document(self, monkeypatch):
        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return _fake_doc_row(status="stored_partial")

            async def fetch(self, *_a, **_kw):
                return []

        monkeypatch.setattr(api, "_db_pool", _FakePool(Conn()))
        result = await get_doc_details("eab0aff1-16ee-4033-8fb2-caf8e6a43feb")
        assert result.title == "테스트 문서"
        assert result.status == "stored_partial"

    async def test_trace_with_null_timestamps(self, monkeypatch):
        trace = {**_fake_trace_row(), "started_at": None, "ended_at": None}

        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return _fake_doc_row()

            async def fetch(self, query, *_a, **_kw):
                if "agent_traces" in query:
                    return [trace]
                return []

        monkeypatch.setattr(api, "_db_pool", _FakePool(Conn()))
        result = await get_doc_details("eab0aff1-16ee-4033-8fb2-caf8e6a43feb")
        assert result.agent_traces[0].started_at is None
        assert result.agent_traces[0].ended_at is None
