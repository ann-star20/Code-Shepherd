"""TDD: FastAPI SSE 파이프라인 스트림 엔드포인트 검증.

테스트 계층
  Unit  (U*) : 순수 헬퍼 함수 - DB 없음
  State (S*) : _state_to_step_updates 분기 검증
  Endpoint (E*): StreamingResponse 통합 검증 (FakePool 사용)
"""
import json
import uuid
from typing import AsyncIterator
import pytest
import asyncio


# ── Fake DB 인프라 (단계별 이벤트 제어) ────────────────────────────────────────

class _FakeRow(dict):
    """asyncpg Record를 흉내 내는 dict."""


class _FakeConn:
    def __init__(self, logs, doc_state):
        self._logs      = logs
        self._doc_state = doc_state
        self.fetch_call_count = 0

    async def fetch(self, query: str, *args):
        self.fetch_call_count += 1
        return [_FakeRow(r) for r in self._logs]

    async def fetchrow(self, query: str, *args):
        if self._doc_state:
            return _FakeRow({"state": self._doc_state})
        return None


class _AcquireCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *_):
        pass


class _FakePool:
    def __init__(self, logs=(), doc_state: str | None = None):
        self.conn = _FakeConn(logs, doc_state)

    def acquire(self):
        return _AcquireCtx(self.conn)


# ─────────────────────────────────────────────────────────────────────────────
# U-tests: _format_sse 순수 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

class TestFormatSSE:
    def test_U01_log_event_format(self):
        """data: JSON 한 줄 + 빈 줄 두 개로 종료."""
        from app.interfaces.api.pipeline import _format_sse
        result = _format_sse({"type": "log", "message": "hello world"})
        assert result == 'data: {"type": "log", "message": "hello world"}\n\n'

    def test_U02_step_update_event_format(self):
        """단일채널: data: JSON 으로 type+payload 직렬화."""
        from app.interfaces.api.pipeline import _format_sse
        result = _format_sse({"type": "step_update", "agent": "Crawler", "status": "DONE"})
        assert result.startswith("data: ")
        assert '"type": "step_update"' in result
        assert '"agent": "Crawler"' in result
        assert result.endswith("\n\n")

    def test_U03_heartbeat_format(self):
        """heartbeat 이벤트는 data: {"type": "heartbeat"} 로 전송."""
        from app.interfaces.api.pipeline import _format_sse
        result = _format_sse({"type": "heartbeat"})
        assert result.startswith("data: ")
        assert '"type": "heartbeat"' in result
        assert result.endswith("\n\n")

    def test_U04_newline_preserved(self):
        """SSE 각 메시지는 항상 \\n\\n 으로 분리된다."""
        from app.interfaces.api.pipeline import _format_sse
        result = _format_sse({"type": "log", "message": "x"})
        assert result.endswith("\n\n"), "SSE 메시지는 빈 줄 두 개로 끝나야 합니다"


# ─────────────────────────────────────────────────────────────────────────────
# S-tests: _state_to_step_updates 분기 검증
# ─────────────────────────────────────────────────────────────────────────────

class TestStateToStepUpdates:
    def test_S01_crawling_input_done(self):
        from app.interfaces.api.pipeline import _state_to_step_updates
        updates = _state_to_step_updates("CRAWLING")
        assert {"agent": "Input", "status": "DONE"} in updates

    def test_S02_crawling_crawler_running(self):
        from app.interfaces.api.pipeline import _state_to_step_updates
        updates = _state_to_step_updates("CRAWLING")
        assert {"agent": "Crawler", "status": "RUNNING"} in updates

    def test_S03_extracted_crawler_done(self):
        from app.interfaces.api.pipeline import _state_to_step_updates
        updates = _state_to_step_updates("EXTRACTED")
        assert {"agent": "Crawler", "status": "DONE"} in updates

    def test_S04_extracted_extractor_done(self):
        from app.interfaces.api.pipeline import _state_to_step_updates
        updates = _state_to_step_updates("EXTRACTED")
        assert {"agent": "Extractor", "status": "DONE"} in updates

    def test_S05_committed_writer_done(self):
        from app.interfaces.api.pipeline import _state_to_step_updates
        updates = _state_to_step_updates("COMMITTED")
        assert {"agent": "Writer", "status": "DONE"} in updates

    def test_S06_failed_returns_empty(self):
        from app.interfaces.api.pipeline import _state_to_step_updates
        updates = _state_to_step_updates("FAILED")
        assert updates == []

    def test_S07_unknown_state_returns_empty(self):
        from app.interfaces.api.pipeline import _state_to_step_updates
        updates = _state_to_step_updates("PENDING")
        assert updates == []


# ─────────────────────────────────────────────────────────────────────────────
# E-tests: SSE 스트림 엔드포인트 통합
# ─────────────────────────────────────────────────────────────────────────────

class TestSSEEndpoint:
    """FastAPI TestClient를 통한 SSE 엔드포인트 통합 검증."""

    def _make_app(self, logs=(), doc_state: str | None = None):
        """FakePool을 주입한 테스트용 FastAPI 앱 생성."""
        from fastapi import FastAPI
        from app.interfaces.api.pipeline import router
        app = FastAPI()
        app.include_router(router)
        app.state.pool = _FakePool(logs=logs, doc_state=doc_state)
        return app

    def test_E01_content_type_is_event_stream(self):
        """SSE 엔드포인트는 text/event-stream 을 반환해야 한다."""
        from fastapi.testclient import TestClient
        session_id = str(uuid.uuid4())
        # COMMITTED 상태를 즉시 반환 → 루프가 바로 종료됨
        app = self._make_app(doc_state="COMMITTED")

        with TestClient(app) as client:
            with client.stream("GET", f"/api/pipeline/stream/{session_id}") as resp:
                assert resp.status_code == 200
                assert "text/event-stream" in resp.headers["content-type"]

    def test_E02_emits_step_update_on_committed(self):
        """COMMITTED 문서 상태 → step_update Writer:DONE 이벤트가 스트림에 포함된다."""
        from fastapi.testclient import TestClient
        session_id = str(uuid.uuid4())
        app = self._make_app(doc_state="COMMITTED")

        with TestClient(app) as client:
            with client.stream("GET", f"/api/pipeline/stream/{session_id}") as resp:
                content = b""
                for chunk in resp.iter_bytes():
                    content += chunk
                    if b"Writer" in content:
                        break

        text = content.decode()
        assert "step_update" in text
        assert "Writer" in text
        assert "DONE" in text

    def test_E03_emits_log_event_for_pipeline_log(self):
        """pipeline_logs 행이 있으면 event: log 이벤트가 스트림에 포함된다."""
        from fastapi.testclient import TestClient
        session_id = str(uuid.uuid4())
        log_rows = [
            {"agent": "Crawler", "level": "INFO", "message": "크롤링 완료", "created_at": "2024-01-01 00:00:00"},
        ]
        app = self._make_app(logs=log_rows, doc_state="COMMITTED")

        with TestClient(app) as client:
            with client.stream("GET", f"/api/pipeline/stream/{session_id}") as resp:
                content = b""
                for chunk in resp.iter_bytes():
                    content += chunk
                    if "크롤링".encode() in content or b"COMMITTED" in content:
                        break

        text = content.decode()
        assert '"type": "log"' in text
        assert "크롤링 완료" in text
