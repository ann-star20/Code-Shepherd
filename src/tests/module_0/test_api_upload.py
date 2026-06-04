from __future__ import annotations

from io import BytesIO

import pytest
from fastapi import BackgroundTasks, HTTPException, UploadFile

import module_0_kms.api as api
from module_0_kms.api import _status_message, get_document_status


class _AcquireContext:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakePool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return _AcquireContext(self.conn)


class _Pipeline:
    async def ainvoke(self, _state):
        raise AssertionError("Upload request should not run the pipeline inline")


@pytest.mark.asyncio
async def test_upload_returns_processing_and_queues_background_task(monkeypatch):
    inserts = []

    class Conn:
        async def execute(self, query, *params):
            inserts.append((query, params))

    monkeypatch.setattr(api, "_db_pool", _FakePool(Conn()))
    monkeypatch.setattr(api, "_pipeline", _Pipeline())

    background_tasks = BackgroundTasks()
    upload = UploadFile(filename="guide.md", file=BytesIO(b"# Guide"))

    response = await api.upload_document(
        background_tasks=background_tasks,
        file=upload,
        source="upload",
    )

    assert response.status == "processing"
    assert response.chunk_count == 0
    assert len(background_tasks.tasks) == 1
    assert inserts


# ---------------------------------------------------------------------------
# get_document_status
# ---------------------------------------------------------------------------

class TestGetDocumentStatus:
    async def test_existing_doc_returns_status(self, monkeypatch):
        _DOC_ID = "00000000-0000-0000-0000-000000000001"

        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return {"upload_status": "stored"}

            async def fetch(self, *_a, **_kw):
                return []

        monkeypatch.setattr(api, "_db_pool", _FakePool(Conn()))
        result = await get_document_status(_DOC_ID)
        assert result.status == "stored"
        assert result.doc_id == _DOC_ID

    async def test_status_query_passes_uuid_not_string(self, monkeypatch):
        """fetchrow에 UUID 객체가 전달돼야 한다 — 문자열이면 asyncpg가 UUID 컬럼에 매칭 안 함."""
        from uuid import UUID as _UUID
        _DOC_ID = "0c3fa8d1-3042-4cb9-84ad-479a28766b71"
        captured = {}

        class Conn:
            async def fetchrow(self, query, *params):
                captured["params"] = params
                return {"upload_status": "processing"}

            async def fetch(self, *_a, **_kw):
                return []

        monkeypatch.setattr(api, "_db_pool", _FakePool(Conn()))
        await get_document_status(_DOC_ID)

        assert captured.get("params"), "fetchrow에 파라미터가 전달되지 않음"
        first_param = captured["params"][0]
        assert isinstance(first_param, _UUID), (
            f"fetchrow 첫 번째 파라미터가 UUID여야 하는데 {type(first_param).__name__}('{first_param}')임"
        )

    async def test_invalid_uuid_format_raises_422(self, monkeypatch):
        """잘못된 UUID 형식은 404가 아닌 422를 반환해야 한다."""

        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return None

        monkeypatch.setattr(api, "_db_pool", _FakePool(Conn()))
        with pytest.raises(HTTPException) as exc:
            await get_document_status("not-a-valid-uuid")
        assert exc.value.status_code == 422

    async def test_missing_doc_raises_404(self, monkeypatch):
        _NONEXISTENT_ID = "ffffffff-ffff-ffff-ffff-ffffffffffff"

        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return None

        monkeypatch.setattr(api, "_db_pool", _FakePool(Conn()))
        with pytest.raises(HTTPException) as exc:
            await get_document_status(_NONEXISTENT_ID)
        assert exc.value.status_code == 404
        assert _NONEXISTENT_ID in exc.value.detail

    async def test_processing_status_returned(self, monkeypatch):
        _DOC_ID = "00000000-0000-0000-0000-000000000002"

        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return {"upload_status": "processing"}

            async def fetch(self, *_a, **_kw):
                return []

        monkeypatch.setattr(api, "_db_pool", _FakePool(Conn()))
        result = await get_document_status(_DOC_ID)
        assert result.status == "processing"
        assert result.current_stage is None


# ---------------------------------------------------------------------------
# _status_message
# ---------------------------------------------------------------------------

class TestStatusMessage:
    def test_stored_status(self):
        state = {"status": "stored", "doc_id": "x"}
        assert "저장" in _status_message(state)

    def test_hitl_pending_with_issues(self):
        state = {"status": "hitl_pending", "quality_issues": ["이슈1", "이슈2", "이슈3"]}
        msg = _status_message(state)
        assert "수동 검토" in msg
        assert "이슈1" in msg
        # 최대 2개만 포함
        assert "이슈3" not in msg

    def test_hitl_pending_chunk_issues_fallback(self):
        state = {"status": "hitl_pending", "quality_issues": [], "chunk_validation_issues": ["청크 오류"]}
        msg = _status_message(state)
        assert "청크 오류" in msg

    def test_failed_with_error(self):
        state = {"status": "failed", "error": "파이프라인 오류"}
        msg = _status_message(state)
        assert "파이프라인 오류" in msg

    def test_failed_without_error(self):
        state = {"status": "failed"}
        msg = _status_message(state)
        assert "알 수 없는 오류" in msg

    def test_unknown_status_returned_as_is(self):
        state = {"status": "processing"}
        assert _status_message(state) == "processing"

    def test_empty_status(self):
        state = {}
        assert _status_message(state) == ""


# ---------------------------------------------------------------------------
# BUG-25: DB 커넥션 끊김 시 500 대신 503 반환
# Cloud SQL 유휴 timeout으로 asyncpg 커넥션이 끊긴 상태에서
# upload_document가 호출되면 ConnectionRefusedError가 처리되지 않아 500이 됨.
# ---------------------------------------------------------------------------

class _ConnectionRefusedPool:
    """pool.acquire() 진입 시 ConnectionRefusedError를 발생시키는 Fake Pool."""

    class _Context:
        async def __aenter__(self):
            raise ConnectionRefusedError("[Errno 111] Connection refused")

        async def __aexit__(self, *_):
            return False

    def acquire(self):
        return self._Context()


@pytest.mark.asyncio
async def test_upload_returns_503_on_db_connection_refused(monkeypatch):
    """
    DB 커넥션이 끊긴 상태(Cloud SQL idle timeout)에서 업로드 요청 시
    처리되지 않은 500이 아닌 503 Service Unavailable을 반환해야 한다.
    """
    monkeypatch.setattr(api, "_db_pool", _ConnectionRefusedPool())
    monkeypatch.setattr(api, "_pipeline", _Pipeline())

    with pytest.raises(HTTPException) as exc:
        await api.upload_document(
            background_tasks=BackgroundTasks(),
            file=UploadFile(filename="test.md", file=BytesIO(b"# Guide")),
            source="upload",
        )

    assert exc.value.status_code == 503, (
        f"DB 커넥션 오류 시 503이어야 하는데 {exc.value.status_code}이 반환됨"
    )
    assert "DB" in exc.value.detail or "데이터베이스" in exc.value.detail or "연결" in exc.value.detail


# ---------------------------------------------------------------------------
# T2: Content-Length 선행 검사 — 파일 본문 미적재 413 반환 (RED → GREEN)
# ---------------------------------------------------------------------------

class _FakeConnForT2:
    async def execute(self, *_a, **_kw):
        pass

    async def executemany(self, *_a, **_kw):
        pass


class _TrackingBytesIO(BytesIO):
    """read() 호출 여부를 추적하는 BytesIO."""
    def __init__(self, data: bytes):
        super().__init__(data)
        self.read_calls: list[int] = []

    def read(self, size: int = -1) -> bytes:
        self.read_calls.append(size)
        return super().read(size)


@pytest.mark.asyncio
async def test_upload_rejects_oversized_file_via_size_without_reading(monkeypatch):
    """
    file.size (Content-Length)가 MAX_UPLOAD_BYTES 초과 시,
    파일 본문을 읽지 않고 즉시 413을 반환해야 한다.
    동시 10개 요청에서 10×50MB = 500MB 메모리 spike를 방지하는 핵심 검사.
    """
    tracking_io = _TrackingBytesIO(b"small actual content")
    oversized_file = UploadFile(
        filename="huge.pdf",
        file=tracking_io,
        size=60 * 1024 * 1024,  # 60MB — Content-Length 초과 선언
    )

    monkeypatch.setattr(api, "_db_pool", _FakePool(_FakeConnForT2()))
    monkeypatch.setattr(api, "_pipeline", _Pipeline())

    with pytest.raises(HTTPException) as exc:
        await api.upload_document(
            background_tasks=BackgroundTasks(),
            file=oversized_file,
            source="upload",
        )

    assert exc.value.status_code == 413
    assert tracking_io.read_calls == [], (
        "file.size 초과 시 파일 본문을 읽으면 안 된다 (메모리 spike 유발)"
    )


@pytest.mark.asyncio
async def test_upload_413_detail_contains_size_info(monkeypatch):
    """413 응답에 파일 크기 정보가 포함되어야 한다."""
    oversized_file = UploadFile(
        filename="huge.pdf",
        file=BytesIO(b"x"),
        size=60 * 1024 * 1024,
    )

    monkeypatch.setattr(api, "_db_pool", _FakePool(_FakeConnForT2()))
    monkeypatch.setattr(api, "_pipeline", _Pipeline())

    with pytest.raises(HTTPException) as exc:
        await api.upload_document(
            background_tasks=BackgroundTasks(),
            file=oversized_file,
            source="upload",
        )

    assert exc.value.status_code == 413
    assert "50" in exc.value.detail, "413 메시지에 최대 크기(50MB) 정보가 있어야 한다"


@pytest.mark.asyncio
async def test_upload_proceeds_when_size_within_limit(monkeypatch):
    """
    file.size가 MAX_UPLOAD_BYTES 이하면 정상 처리되어야 한다.
    Content-Length 선행 검사가 정상 파일을 차단하면 안 된다.
    """
    tracking_io = _TrackingBytesIO(b"# Valid document content")
    normal_file = UploadFile(
        filename="guide.md",
        file=tracking_io,
        size=1024,  # 1KB — 정상 범위
    )

    monkeypatch.setattr(api, "_db_pool", _FakePool(_FakeConnForT2()))
    monkeypatch.setattr(api, "_pipeline", _Pipeline())

    response = await api.upload_document(
        background_tasks=BackgroundTasks(),
        file=normal_file,
        source="upload",
    )

    assert response.status == "processing"
    assert tracking_io.read_calls != [], "정상 파일은 본문을 읽어야 한다"


@pytest.mark.asyncio
async def test_upload_rejects_oversized_when_size_is_none_fallback(monkeypatch):
    """
    file.size=None (Content-Length 미전송)이어도,
    실제 읽은 콘텐츠가 초과하면 413을 반환해야 한다 (기존 폴백 동작 유지).
    """
    large_content = b"x" * (51 * 1024 * 1024)  # 51MB
    oversized_no_cl = UploadFile(
        filename="no_cl.pdf",
        file=BytesIO(large_content),
        size=None,  # Content-Length 없음
    )

    monkeypatch.setattr(api, "_db_pool", _FakePool(_FakeConnForT2()))
    monkeypatch.setattr(api, "_pipeline", _Pipeline())

    with pytest.raises(HTTPException) as exc:
        await api.upload_document(
            background_tasks=BackgroundTasks(),
            file=oversized_no_cl,
            source="upload",
        )

    assert exc.value.status_code == 413
