"""Tests for parsing detail fields in GET /kms/docs/{doc_id}/details response."""

from __future__ import annotations

import datetime

import pytest
from fastapi import HTTPException

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


_NOW = datetime.datetime(2026, 5, 30, tzinfo=datetime.timezone.utc)


def _doc_row_with_parsing(
    parser_used: str | None = "pymupdf",
    quality_score: float | None = 0.87,
    doc_complexity: str | None = "LOW",
    parsing_time_ms: int | None = 320,
) -> dict:
    return {
        "title": "파싱 테스트 문서",
        "file_type": "pdf",
        "upload_status": "stored",
        "created_at": _NOW,
        "parser_used": parser_used,
        "quality_score": quality_score,
        "doc_complexity": doc_complexity,
        "parsing_time_ms": parsing_time_ms,
    }


class _ConnWithParsing:
    def __init__(self, doc_row: dict):
        self._doc_row = doc_row

    async def fetchrow(self, *_a, **_kw):
        return self._doc_row

    async def fetch(self, *_a, **_kw):
        return []


_DOC_ID = "00000000-0000-0000-0000-000000000099"


# ---------------------------------------------------------------------------
# DocDetailsResponse에 파싱 상세 필드가 포함되는지 확인
# ---------------------------------------------------------------------------

class TestDocDetailsParsingFields:
    async def test_parser_used_in_response(self, monkeypatch):
        """DocDetailsResponse에 parser_used 필드가 포함된다."""
        monkeypatch.setattr(api, "_db_pool", _FakePool(_ConnWithParsing(_doc_row_with_parsing())))
        result = await get_doc_details(_DOC_ID)
        assert result.parser_used == "pymupdf"

    async def test_quality_score_in_response(self, monkeypatch):
        """quality_score는 BUG-30으로 DB에서 제거됐으므로 항상 None을 반환한다."""
        monkeypatch.setattr(api, "_db_pool", _FakePool(_ConnWithParsing(_doc_row_with_parsing())))
        result = await get_doc_details(_DOC_ID)
        assert result.quality_score is None

    async def test_doc_complexity_in_response(self, monkeypatch):
        """DocDetailsResponse에 doc_complexity 필드가 포함된다."""
        monkeypatch.setattr(api, "_db_pool", _FakePool(_ConnWithParsing(_doc_row_with_parsing())))
        result = await get_doc_details(_DOC_ID)
        assert result.doc_complexity == "LOW"

    async def test_parsing_time_ms_in_response(self, monkeypatch):
        """DocDetailsResponse에 parsing_time_ms 필드가 포함된다."""
        monkeypatch.setattr(api, "_db_pool", _FakePool(_ConnWithParsing(_doc_row_with_parsing())))
        result = await get_doc_details(_DOC_ID)
        assert result.parsing_time_ms == 320


# ---------------------------------------------------------------------------
# 각 필드가 null일 때도 정상 반환
# ---------------------------------------------------------------------------

class TestDocDetailsParsingFieldsNull:
    async def test_null_parser_used_allowed(self, monkeypatch):
        """parser_used가 NULL이어도 오류 없이 반환된다."""
        monkeypatch.setattr(
            api, "_db_pool",
            _FakePool(_ConnWithParsing(_doc_row_with_parsing(parser_used=None)))
        )
        result = await get_doc_details(_DOC_ID)
        assert result.parser_used is None

    async def test_null_quality_score_allowed(self, monkeypatch):
        """quality_score가 NULL이어도 오류 없이 반환된다."""
        monkeypatch.setattr(
            api, "_db_pool",
            _FakePool(_ConnWithParsing(_doc_row_with_parsing(quality_score=None)))
        )
        result = await get_doc_details(_DOC_ID)
        assert result.quality_score is None

    async def test_null_doc_complexity_allowed(self, monkeypatch):
        """doc_complexity가 NULL이어도 오류 없이 반환된다."""
        monkeypatch.setattr(
            api, "_db_pool",
            _FakePool(_ConnWithParsing(_doc_row_with_parsing(doc_complexity=None)))
        )
        result = await get_doc_details(_DOC_ID)
        assert result.doc_complexity is None

    async def test_null_parsing_time_ms_allowed(self, monkeypatch):
        """parsing_time_ms가 NULL이어도 오류 없이 반환된다."""
        monkeypatch.setattr(
            api, "_db_pool",
            _FakePool(_ConnWithParsing(_doc_row_with_parsing(parsing_time_ms=None)))
        )
        result = await get_doc_details(_DOC_ID)
        assert result.parsing_time_ms is None


# ---------------------------------------------------------------------------
# 파싱 상세 값이 DB에서 실제로 읽힘 (다른 값 검증)
# ---------------------------------------------------------------------------

class TestDocDetailsParsingFieldValues:
    async def test_high_complexity_returned(self, monkeypatch):
        """doc_complexity=HIGH 값이 올바르게 반환된다."""
        monkeypatch.setattr(
            api, "_db_pool",
            _FakePool(_ConnWithParsing(_doc_row_with_parsing(doc_complexity="HIGH")))
        )
        result = await get_doc_details(_DOC_ID)
        assert result.doc_complexity == "HIGH"

    async def test_upstage_parser_returned(self, monkeypatch):
        """parser_used=upstage 값이 올바르게 반환된다."""
        monkeypatch.setattr(
            api, "_db_pool",
            _FakePool(_ConnWithParsing(_doc_row_with_parsing(parser_used="upstage")))
        )
        result = await get_doc_details(_DOC_ID)
        assert result.parser_used == "upstage"

    async def test_all_parsing_fields_together(self, monkeypatch):
        """4개 파싱 상세 필드가 동시에 올바르게 반환된다."""
        monkeypatch.setattr(
            api, "_db_pool",
            _FakePool(_ConnWithParsing(_doc_row_with_parsing(
                parser_used="python_docx",
                quality_score=0.95,
                doc_complexity="MEDIUM",
                parsing_time_ms=1500,
            )))
        )
        result = await get_doc_details(_DOC_ID)
        assert result.parser_used == "python_docx"
        assert result.quality_score is None  # BUG-30: quality_score DB 컬럼 제거 → 항상 None
        assert result.doc_complexity == "MEDIUM"
        assert result.parsing_time_ms == 1500
