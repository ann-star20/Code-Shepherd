"""tests/test_documents.py — 문서 중복 검사 + 메타데이터 학습 엔드포인트 테스트."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestCheckDuplicate:
    @patch("app.api.documents.asyncpg.connect", new_callable=AsyncMock)
    def test_returns_not_duplicate_for_unknown_url(self, mock_connect):
        # Arrange
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=None)
        conn.close = AsyncMock()
        mock_connect.return_value = conn

        # Act
        resp = client.post(
            "/documents/check-duplicate",
            json={"url": "https://nestjs.com/docs/security"},
        )

        # Assert
        assert resp.status_code == 200
        assert resp.json() == {"is_duplicate": False, "doc_id": None}

    @patch("app.api.documents.asyncpg.connect", new_callable=AsyncMock)
    def test_returns_duplicate_with_doc_id_for_known_url(self, mock_connect):
        # Arrange
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(
            return_value={"doc_id": "nestjs-security-001", "state": "COMMITTED"}
        )
        conn.close = AsyncMock()
        mock_connect.return_value = conn

        # Act
        resp = client.post(
            "/documents/check-duplicate",
            json={"url": "https://nestjs.com/docs/security"},
        )

        # Assert
        assert resp.status_code == 200
        assert resp.json() == {"is_duplicate": True, "doc_id": "nestjs-security-001"}

    @patch("app.api.documents.asyncpg.connect", new_callable=AsyncMock)
    def test_returns_not_duplicate_for_failed_document(self, mock_connect):
        """state가 COMMITTED가 아니면(FAILED 등) 재파이프라인을 허용한다."""
        # Arrange
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(
            return_value={"doc_id": "nestjs-security-001", "state": "FAILED"}
        )
        conn.close = AsyncMock()
        mock_connect.return_value = conn

        # Act
        resp = client.post(
            "/documents/check-duplicate",
            json={"url": "https://nestjs.com/docs/security"},
        )

        # Assert
        assert resp.status_code == 200
        assert resp.json() == {"is_duplicate": False, "doc_id": None}

    def test_rejects_invalid_url(self):
        # Arrange
        payload = {"url": "not-a-url"}

        # Act
        resp = client.post("/documents/check-duplicate", json=payload)

        # Assert
        assert resp.status_code == 422


class TestLearnMetadata:
    @patch("app.api.documents.asyncpg.connect", new_callable=AsyncMock)
    def test_learn_metadata_returns_learned_status(self, mock_connect):
        # Arrange
        conn = AsyncMock()
        conn.execute = AsyncMock()
        conn.close = AsyncMock()
        mock_connect.return_value = conn
        payload = {
            "framework": "NestJS",
            "pattern": r"nestjs\.io",
            "supported_langs": ["typescript", "javascript"],
            "default_lang": "typescript",
        }

        # Act
        resp = client.post("/documents/metadata/learn", json=payload)

        # Assert
        assert resp.status_code == 200
        assert resp.json() == {"framework": "NestJS", "status": "learned"}
        conn.execute.assert_called_once()

    @patch("app.api.documents.asyncpg.connect", new_callable=AsyncMock)
    def test_learn_metadata_without_default_lang(self, mock_connect):
        # Arrange
        conn = AsyncMock()
        conn.execute = AsyncMock()
        conn.close = AsyncMock()
        mock_connect.return_value = conn
        payload = {
            "framework": "Gin",
            "pattern": r"gin-gonic\.com",
            "supported_langs": ["go"],
        }

        # Act
        resp = client.post("/documents/metadata/learn", json=payload)

        # Assert
        assert resp.status_code == 200
        assert resp.json() == {"framework": "Gin", "status": "learned"}
        args, _ = conn.execute.call_args
        assert args[-1] is None


class TestResumeMetadata:
    @patch("app.api.documents.resume_pipeline")
    @patch("app.api.documents.asyncpg.connect", new_callable=AsyncMock)
    def test_resume_with_framework_updates_document_and_resumes_pipeline(
        self, mock_connect, mock_resume
    ):
        """프레임워크를 입력하면 knowledge_documents 갱신 후 파이프라인 재개."""
        # Arrange
        conn = AsyncMock()
        conn.execute = AsyncMock()
        conn.close = AsyncMock()
        mock_connect.return_value = conn
        payload = {
            "session_id": "sid-1",
            "doc_id": "doc_abc123",
            "url": "https://docs.astro.build/getting-started",
            "framework": "Astro",
            "lang": "TypeScript",
        }

        # Act
        resp = client.post("/documents/metadata/resume", json=payload)

        # Assert
        assert resp.status_code == 202
        assert resp.json() == {"status": "resumed"}
        conn.execute.assert_called_once()
        update_args, _ = conn.execute.call_args
        assert "Astro" in update_args
        assert "doc_abc123" in update_args
        mock_resume.assert_called_once()
        ctx = mock_resume.call_args[0][0]
        assert ctx["doc_id"] == "doc_abc123"
        assert ctx["framework"] == "Astro"
        assert ctx["lang"] == "TypeScript"
        assert ctx["source_prefix"] == "astro"
        assert ctx["skip"] is False

    @patch("app.api.documents.resume_pipeline")
    @patch("app.api.documents.asyncpg.connect", new_callable=AsyncMock)
    def test_resume_without_framework_skips_db_update_and_uses_empty_values(
        self, mock_connect, mock_resume
    ):
        """프레임워크를 입력하지 않고 skip하면 빈 값으로 파이프라인을 재개한다."""
        # Arrange
        conn = AsyncMock()
        conn.execute = AsyncMock()
        conn.close = AsyncMock()
        mock_connect.return_value = conn
        payload = {
            "session_id": "sid-2",
            "doc_id": "doc_def456",
            "url": "https://example.com/unknown",
        }

        # Act
        resp = client.post("/documents/metadata/resume", json=payload)

        # Assert
        assert resp.status_code == 202
        assert resp.json() == {"status": "resumed"}
        conn.execute.assert_not_called()
        mock_resume.assert_called_once()
        ctx = mock_resume.call_args[0][0]
        assert ctx["doc_id"] == "doc_def456"
        assert ctx["framework"] is None
        assert ctx["lang"] is None
        assert ctx["source_prefix"] == "external"
