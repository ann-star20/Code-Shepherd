"""tests/test_pipeline_api.py — 파이프라인 트리거/스트림 HTTP 엔드포인트 테스트."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestTrigger:
    @patch("app.api.pipeline.trigger_pipeline")
    def test_trigger_returns_session_id_and_message(self, mock_trigger):
        # Arrange
        payload = {"doc_id": "https://nestjs.com/docs/security"}

        # Act
        resp = client.post("/pipeline/trigger", json=payload)

        # Assert
        assert resp.status_code == 202
        data = resp.json()
        assert "session_id" in data
        assert "message" in data

    @patch("app.api.pipeline.trigger_pipeline")
    def test_trigger_starts_pipeline_with_doc_id_as_url(self, mock_trigger):
        # Arrange
        payload = {"doc_id": "https://nestjs.com/docs/security"}

        # Act
        resp = client.post("/pipeline/trigger", json=payload)

        # Assert
        session_id = resp.json()["session_id"]
        mock_trigger.assert_called_once_with(session_id, "https://nestjs.com/docs/security")

    def test_trigger_rejects_invalid_url(self):
        # Arrange
        payload = {"doc_id": "not-a-url"}

        # Act
        resp = client.post("/pipeline/trigger", json=payload)

        # Assert
        assert resp.status_code == 422
