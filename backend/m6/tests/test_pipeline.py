"""tests/test_pipeline.py — Celery 파이프라인 태스크 단위 테스트 (mock 기반)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestPrescanTask:
    @patch("app.worker.tasks.asyncio.run")
    @patch("app.worker.tasks._emit")
    def test_prescan_emits_success_event(self, mock_emit, mock_run):
        """prescan 성공 시 step_update 이벤트 발행."""
        mock_run.return_value = {
            "skip": False, "doc_id": "doc_abc123", "url": "https://nestjs.com",
            "session_id": "test-session-id",
        }

        from app.worker.tasks import prescan_task
        ctx = prescan_task.run("test-session-id", "https://nestjs.com")

        mock_emit.assert_called_once()
        event = mock_emit.call_args[0][1]
        assert event["type"] == "step_update"
        assert event["agent"] == "Prescan"
        assert event["status"] == "SUCCESS"

    @patch("app.worker.tasks.asyncio.run")
    @patch("app.worker.tasks._set_failed_sync")
    @patch("app.worker.tasks._emit")
    def test_prescan_sets_failed_on_exception(self, mock_emit, mock_set_failed, mock_run):
        """prescan 예외 발생 시 _set_failed_sync 호출."""
        mock_run.side_effect = RuntimeError("connection refused")

        from app.worker.tasks import prescan_task
        with pytest.raises(Exception):
            prescan_task.run("test-session-id", "https://example.com")

        mock_set_failed.assert_called_once_with("test-session-id")


class TestCrawlTask:
    @patch("app.worker.tasks.asyncio.run")
    @patch("app.worker.tasks._emit")
    def test_crawl_skips_when_flag_set(self, mock_emit, mock_run):
        """skip=True 컨텍스트는 crawl을 건너뜀."""
        from app.worker.tasks import crawl_task
        ctx = {"skip": True, "doc_id": "doc_abc", "session_id": "sid"}
        result = crawl_task.run(ctx)
        mock_run.assert_not_called()
        assert result == ctx

    @patch("app.worker.tasks.asyncio.run")
    @patch("app.worker.tasks._emit")
    def test_crawl_emits_success_event(self, mock_emit, mock_run):
        """crawl 성공 시 Crawler step_update 이벤트."""
        ctx = {"skip": False, "doc_id": "doc_abc", "url": "https://x.com", "session_id": "sid"}
        mock_run.return_value = {**ctx, "chunks": ["chunk1"]}

        from app.worker.tasks import crawl_task
        crawl_task.run(ctx)

        event = mock_emit.call_args[0][1]
        assert event["type"] == "step_update"
        assert event["agent"] == "Crawler"


class TestExtractTask:
    @patch("app.worker.tasks.asyncio.run")
    @patch("app.worker.tasks._emit")
    def test_extract_skips_when_flag_set(self, mock_emit, mock_run):
        """skip=True 컨텍스트는 extract를 건너뜀."""
        from app.worker.tasks import extract_task
        ctx = {"skip": True, "session_id": "sid"}
        result = extract_task.run(ctx)
        mock_run.assert_not_called()

    @patch("app.worker.tasks.asyncio.run")
    @patch("app.worker.tasks._emit")
    def test_extract_emits_extractor_and_finished(self, mock_emit, mock_run):
        """extract 성공 시 Extractor + finished 이벤트 순서대로."""
        ctx = {
            "skip": False, "doc_id": "doc_abc",
            "chunks": ["text"], "session_id": "sid",
            "source_prefix": "external",
        }
        mock_run.return_value = {**ctx, "staged": 1}

        from app.worker.tasks import extract_task
        extract_task.run(ctx)

        calls = [c[0][1] for c in mock_emit.call_args_list]
        types = [c["type"] for c in calls]
        assert "step_update" in types
        assert "finished" in types


class TestChunkText:
    def test_short_text_single_chunk(self):
        from app.worker.tasks import _chunk_text
        chunks = _chunk_text("hello world", max_len=4000)
        assert len(chunks) == 1
        assert chunks[0] == "hello world"

    def test_long_text_multiple_chunks(self):
        from app.worker.tasks import _chunk_text
        text = "\n\n".join(["paragraph"] * 100)
        chunks = _chunk_text(text, max_len=50)
        assert len(chunks) > 1

    def test_empty_text_returns_single_empty(self):
        from app.worker.tasks import _chunk_text
        chunks = _chunk_text("", max_len=4000)
        assert chunks == [""]


class TestMockExtract:
    def test_returns_list_with_one_concept(self):
        from app.worker.tasks import _mock_extract
        result = _mock_extract("some text about security", {"framework": "Django", "source_prefix": "django"})
        assert len(result) == 1
        assert result[0]["concept_name"].startswith("concept_Django")
        assert "Django" in result[0]["domains"] or "django" in result[0]["domains"]

    def test_concept_name_deterministic(self):
        from app.worker.tasks import _mock_extract
        chunk = "same chunk"
        ctx = {"framework": "NestJS", "source_prefix": "nestjs"}
        r1 = _mock_extract(chunk, ctx)
        r2 = _mock_extract(chunk, ctx)
        assert r1[0]["concept_name"] == r2[0]["concept_name"]


class TestWriteGraphTask:
    @patch("app.worker.tasks.asyncio.run")
    @patch("app.worker.tasks._emit")
    def test_write_graph_emits_finished(self, mock_emit, mock_run):
        """write_graph 성공 시 GraphWriter + finished 이벤트."""
        mock_run.return_value = {
            "session_id": "test-sid",
            "summary": {"MERGE": 1, "RELATED_TO": 0, "NEW": 0},
        }

        from app.worker.tasks import write_graph_task
        write_graph_task.run("test-sid")

        events = [c[0][1]["type"] for c in mock_emit.call_args_list]
        assert "step_update" in events
        assert "finished" in events
