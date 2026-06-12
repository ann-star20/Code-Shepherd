"""tests/test_staging.py — 스테이징 API 엔드포인트 테스트."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestListStaging:
    @patch("app.api.staging.asyncpg.connect", new_callable=AsyncMock)
    def test_returns_empty_list_for_unknown_session(self, mock_connect):
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[])
        conn.close = AsyncMock()
        mock_connect.return_value = conn

        session_id = str(uuid.uuid4())
        resp = client.get(f"/api/staging/{session_id}")
        assert resp.status_code == 200
        assert resp.json() == []


class TestApprove:
    @patch("app.api.staging.asyncpg.connect", new_callable=AsyncMock)
    def test_approve_draft_returns_approved(self, mock_connect):
        staging_id = str(uuid.uuid4())
        conn = AsyncMock()
        conn.__aenter__ = AsyncMock(return_value=conn)
        conn.__aexit__ = AsyncMock(return_value=False)
        conn.transaction = MagicMock(return_value=conn)
        conn.fetchrow = AsyncMock(return_value={"id": uuid.UUID(staging_id), "state": "DRAFT"})
        conn.execute = AsyncMock()
        conn.close = AsyncMock()
        mock_connect.return_value = conn

        resp = client.post(f"/api/staging/{staging_id}/approve")
        assert resp.status_code == 200
        assert resp.json()["state"] == "APPROVED"

    @patch("app.api.staging.asyncpg.connect", new_callable=AsyncMock)
    def test_approve_non_draft_returns_400(self, mock_connect):
        staging_id = str(uuid.uuid4())
        conn = AsyncMock()
        conn.__aenter__ = AsyncMock(return_value=conn)
        conn.__aexit__ = AsyncMock(return_value=False)
        conn.transaction = MagicMock(return_value=conn)
        conn.fetchrow = AsyncMock(return_value={"id": uuid.UUID(staging_id), "state": "COMMITTED"})
        conn.execute = AsyncMock()
        conn.close = AsyncMock()
        mock_connect.return_value = conn

        resp = client.post(f"/api/staging/{staging_id}/approve")
        assert resp.status_code == 400


class TestReject:
    @patch("app.api.staging.asyncpg.connect", new_callable=AsyncMock)
    def test_reject_draft_returns_rejected(self, mock_connect):
        staging_id = str(uuid.uuid4())
        conn = AsyncMock()
        conn.execute = AsyncMock(return_value="UPDATE 1")
        conn.close = AsyncMock()
        mock_connect.return_value = conn

        resp = client.post(f"/api/staging/{staging_id}/reject")
        assert resp.status_code == 200
        assert resp.json()["state"] == "REJECTED"


class TestDiff:
    @patch("app.api.staging.asyncpg.connect", new_callable=AsyncMock)
    def test_diff_returns_incoming_and_existing(self, mock_connect):
        staging_id = str(uuid.uuid4())
        concept = {
            "concept_name": "XSS", "domains": ["security"],
            "description_ko": "테스트", "aliases": [], "mechanism": [],
        }
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(side_effect=[
            {
                "concept_json": json.dumps(concept),
                "infer_action": "MERGE",
                "target_concept_name": "XSS",
            },
            {
                "concept_name": "XSS",
                "aliases": ["Cross-Site Scripting"],
                "description_ko": "기존 설명",
                "severity": "high",
                "domains": ["security"],
            },
        ])
        conn.close = AsyncMock()
        mock_connect.return_value = conn

        resp = client.get(f"/api/staging/{staging_id}/diff")
        assert resp.status_code == 200
        data = resp.json()
        assert data["incoming"]["concept_name"] == "XSS"
        assert data["infer_action"] == "MERGE"

    @patch("app.api.staging.asyncpg.connect", new_callable=AsyncMock)
    def test_diff_returns_404_for_unknown_id(self, mock_connect):
        staging_id = str(uuid.uuid4())
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=None)
        conn.close = AsyncMock()
        mock_connect.return_value = conn

        resp = client.get(f"/api/staging/{staging_id}/diff")
        assert resp.status_code == 404


class TestCommit:
    @patch("app.api.staging.write_graph_task")
    def test_commit_triggers_write_graph(self, mock_task):
        mock_task.apply_async = MagicMock()
        session_id = str(uuid.uuid4())

        resp = client.post("/api/staging/commit", json={"session_id": session_id})
        assert resp.status_code == 202
        assert resp.json()["status"] == "write_graph_triggered"
        mock_task.apply_async.assert_called_once_with(args=[session_id])
