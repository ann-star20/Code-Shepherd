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
        conn.fetchrow = AsyncMock(return_value={"doc_id": "nestjs-security-001"})
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
