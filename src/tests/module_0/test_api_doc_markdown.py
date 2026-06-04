"""Tests for GET /kms/docs/{doc_id}/markdown endpoint."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

import module_0_kms.api as api
from module_0_kms.api import get_doc_markdown


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


class _FakeStorage:
    def __init__(self, content: bytes | None = None, raise_exc: Exception | None = None):
        self._content = content
        self._raise_exc = raise_exc
        self.loaded_path: str | None = None

    async def load(self, path: str) -> bytes:
        self.loaded_path = path
        if self._raise_exc is not None:
            raise self._raise_exc
        return self._content or b""


def _doc_row_with_markdown(markdown_path: str | None = "markdown/abc/raw.md") -> dict:
    return {
        "markdown_path": markdown_path,
        "upload_status": "stored",
    }


# ---------------------------------------------------------------------------
# UUID 검증
# ---------------------------------------------------------------------------

class TestInvalidDocId:
    async def test_invalid_uuid_raises_422(self, monkeypatch):
        monkeypatch.setattr(api, "_db_pool", _FakePool(None))
        monkeypatch.setattr(api, "_storage", _FakeStorage())

        with pytest.raises(HTTPException) as exc_info:
            await get_doc_markdown("not-a-uuid")
        assert exc_info.value.status_code == 422

    async def test_partial_uuid_raises_422(self, monkeypatch):
        monkeypatch.setattr(api, "_db_pool", _FakePool(None))
        monkeypatch.setattr(api, "_storage", _FakeStorage())

        with pytest.raises(HTTPException) as exc_info:
            await get_doc_markdown("12345-bad")
        assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# 문서 미존재
# ---------------------------------------------------------------------------

class TestDocNotFound:
    async def test_missing_doc_raises_404(self, monkeypatch):
        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return None

        monkeypatch.setattr(api, "_db_pool", _FakePool(Conn()))
        monkeypatch.setattr(api, "_storage", _FakeStorage())

        with pytest.raises(HTTPException) as exc_info:
            await get_doc_markdown("00000000-0000-0000-0000-000000000001")
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# markdown_path 없음
# ---------------------------------------------------------------------------

class TestMarkdownPathMissing:
    async def test_null_markdown_path_raises_404(self, monkeypatch):
        """documents.markdown_path가 NULL이면 404를 반환한다."""
        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return _doc_row_with_markdown(markdown_path=None)

        monkeypatch.setattr(api, "_db_pool", _FakePool(Conn()))
        monkeypatch.setattr(api, "_storage", _FakeStorage())

        with pytest.raises(HTTPException) as exc_info:
            await get_doc_markdown("00000000-0000-0000-0000-000000000001")
        assert exc_info.value.status_code == 404
        assert "markdown" in exc_info.value.detail.lower()

    async def test_empty_markdown_path_raises_404(self, monkeypatch):
        """documents.markdown_path가 빈 문자열이면 404를 반환한다."""
        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return _doc_row_with_markdown(markdown_path="")

        monkeypatch.setattr(api, "_db_pool", _FakePool(Conn()))
        monkeypatch.setattr(api, "_storage", _FakeStorage())

        with pytest.raises(HTTPException) as exc_info:
            await get_doc_markdown("00000000-0000-0000-0000-000000000001")
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Storage 오류
# ---------------------------------------------------------------------------

class TestStorageErrors:
    async def test_file_not_found_in_storage_raises_404(self, monkeypatch):
        """Storage에 파일이 없으면 404를 반환한다."""
        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return _doc_row_with_markdown()

        storage = _FakeStorage(raise_exc=FileNotFoundError("GCS에 파일 없음"))
        monkeypatch.setattr(api, "_db_pool", _FakePool(Conn()))
        monkeypatch.setattr(api, "_storage", storage)

        with pytest.raises(HTTPException) as exc_info:
            await get_doc_markdown("00000000-0000-0000-0000-000000000001")
        assert exc_info.value.status_code == 404

    async def test_storage_general_error_raises_503(self, monkeypatch):
        """Storage 일반 오류는 503을 반환한다."""
        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return _doc_row_with_markdown()

        storage = _FakeStorage(raise_exc=RuntimeError("GCS 연결 실패"))
        monkeypatch.setattr(api, "_db_pool", _FakePool(Conn()))
        monkeypatch.setattr(api, "_storage", storage)

        with pytest.raises(HTTPException) as exc_info:
            await get_doc_markdown("00000000-0000-0000-0000-000000000001")
        assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# 정상 반환
# ---------------------------------------------------------------------------

class TestGetDocMarkdownSuccess:
    async def test_returns_markdown_content(self, monkeypatch):
        """정상 케이스에서 Markdown 텍스트를 반환한다."""
        markdown_text = "# 제목\n\n본문 내용입니다."

        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return _doc_row_with_markdown("markdown/abc/raw.md")

        storage = _FakeStorage(content=markdown_text.encode("utf-8"))
        monkeypatch.setattr(api, "_db_pool", _FakePool(Conn()))
        monkeypatch.setattr(api, "_storage", storage)

        result = await get_doc_markdown("00000000-0000-0000-0000-000000000001")
        assert result.content == markdown_text

    async def test_response_includes_doc_id(self, monkeypatch):
        """응답에 doc_id가 포함된다."""
        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return _doc_row_with_markdown()

        storage = _FakeStorage(content=b"# content")
        doc_id = "00000000-0000-0000-0000-000000000002"
        monkeypatch.setattr(api, "_db_pool", _FakePool(Conn()))
        monkeypatch.setattr(api, "_storage", storage)

        result = await get_doc_markdown(doc_id)
        assert result.doc_id == doc_id

    async def test_response_includes_markdown_path(self, monkeypatch):
        """응답에 storage 경로가 포함된다."""
        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return _doc_row_with_markdown("markdown/xyz/raw.md")

        storage = _FakeStorage(content=b"content")
        monkeypatch.setattr(api, "_db_pool", _FakePool(Conn()))
        monkeypatch.setattr(api, "_storage", storage)

        result = await get_doc_markdown("00000000-0000-0000-0000-000000000001")
        assert result.markdown_path == "markdown/xyz/raw.md"

    async def test_storage_load_called_with_correct_path(self, monkeypatch):
        """storage.load()가 documents.markdown_path 경로로 호출된다."""
        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return _doc_row_with_markdown("markdown/test-doc/raw.md")

        storage = _FakeStorage(content=b"# content")
        monkeypatch.setattr(api, "_db_pool", _FakePool(Conn()))
        monkeypatch.setattr(api, "_storage", storage)

        await get_doc_markdown("00000000-0000-0000-0000-000000000001")
        assert storage.loaded_path == "markdown/test-doc/raw.md"

    async def test_storage_not_initialized_raises_runtime_error(self, monkeypatch):
        """_storage가 None이면 RuntimeError가 발생한다."""
        monkeypatch.setattr(api, "_storage", None)

        with pytest.raises(RuntimeError):
            await get_doc_markdown("00000000-0000-0000-0000-000000000001")
