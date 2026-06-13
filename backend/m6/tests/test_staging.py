"""tests/test_staging.py — 스테이징 API 엔드포인트 테스트."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestListStaging:
    @patch("app.api.staging.asyncpg.connect", new_callable=AsyncMock)
    def test_returns_empty_items_for_unknown_session(self, mock_connect):
        # Arrange
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[])
        conn.close = AsyncMock()
        mock_connect.return_value = conn
        session_id = str(uuid.uuid4())

        # Act
        resp = client.get(f"/staging/{session_id}")

        # Assert
        assert resp.status_code == 200
        assert resp.json() == {"items": []}

    @patch("app.api.staging.asyncpg.connect", new_callable=AsyncMock)
    def test_returns_graph_node_shaped_items(self, mock_connect):
        # Arrange
        staging_id = str(uuid.uuid4())
        concept = {
            "concept_name": "XSS",
            "domains": ["security"],
            "description_ko": "테스트 설명",
            "aliases": ["Cross-Site Scripting"],
            "mechanism": ["reflected", "stored"],
            "cwe_id": "CWE-79",
            "owasp_id": "A03:2021",
            "severity": "high",
        }
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[
            {
                "staging_id": staging_id,
                "concept_json": json.dumps(concept),
                "state": "DRAFT",
                "infer_action": "NEW",
                "infer_confidence": 0.95,
                "target_concept_name": None,
            }
        ])
        conn.close = AsyncMock()
        mock_connect.return_value = conn
        session_id = str(uuid.uuid4())

        # Act
        resp = client.get(f"/staging/{session_id}")

        # Assert
        item = resp.json()["items"][0]
        assert item["id"] == "XSS"
        assert item["name"] == "XSS"
        assert item["status"] == "DRAFT"
        assert item["domains"] == ["security"]
        assert item["cwe_id"] == "CWE-79"
        assert item["owasp_id"] == "A03:2021"
        assert item["severity"] == "high"
        assert item["mechanisms"] == ["reflected", "stored"]
        assert item["aliases"] == ["Cross-Site Scripting"]
        assert item["staging_id"] == staging_id
        assert item["state"] == "DRAFT"

    @patch("app.api.staging.asyncpg.connect", new_callable=AsyncMock)
    def test_merge_infer_action_yields_merge_pending_status(self, mock_connect):
        # Arrange
        staging_id = str(uuid.uuid4())
        concept = {"concept_name": "CSRF", "domains": ["security"]}
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[
            {
                "staging_id": staging_id,
                "concept_json": json.dumps(concept),
                "state": "DRAFT",
                "infer_action": "MERGE",
                "infer_confidence": 0.9,
                "target_concept_name": "CSRF",
            }
        ])
        conn.close = AsyncMock()
        mock_connect.return_value = conn
        session_id = str(uuid.uuid4())

        # Act
        resp = client.get(f"/staging/{session_id}")

        # Assert
        item = resp.json()["items"][0]
        assert item["status"] == "MERGE_PENDING"
        assert item["target_concept_name"] == "CSRF"


class TestApprove:
    @patch("app.api.staging.asyncpg.connect", new_callable=AsyncMock)
    def test_approve_single_draft_item_returns_approved(self, mock_connect):
        # Arrange
        staging_id = str(uuid.uuid4())
        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value=1)
        conn.__aenter__ = AsyncMock(return_value=conn)
        conn.__aexit__ = AsyncMock(return_value=False)
        conn.transaction = MagicMock(return_value=conn)
        conn.fetchrow = AsyncMock(return_value={"id": uuid.UUID(staging_id), "state": "DRAFT"})
        conn.execute = AsyncMock()
        conn.close = AsyncMock()
        mock_connect.return_value = conn

        # Act
        resp = client.post(f"/staging/{staging_id}/approve")

        # Assert
        assert resp.status_code == 200
        assert resp.json() == {"id": staging_id, "state": "APPROVED"}

    @patch("app.api.staging.asyncpg.connect", new_callable=AsyncMock)
    def test_approve_single_non_draft_returns_400(self, mock_connect):
        # Arrange
        staging_id = str(uuid.uuid4())
        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value=1)
        conn.__aenter__ = AsyncMock(return_value=conn)
        conn.__aexit__ = AsyncMock(return_value=False)
        conn.transaction = MagicMock(return_value=conn)
        conn.fetchrow = AsyncMock(return_value={"id": uuid.UUID(staging_id), "state": "COMMITTED"})
        conn.execute = AsyncMock()
        conn.close = AsyncMock()
        mock_connect.return_value = conn

        # Act
        resp = client.post(f"/staging/{staging_id}/approve")

        # Assert
        assert resp.status_code == 400

    @patch("app.api.staging.asyncpg.connect", new_callable=AsyncMock)
    def test_approve_session_bulk_returns_approved_count(self, mock_connect):
        # Arrange
        session_id = str(uuid.uuid4())
        conn = AsyncMock()
        conn.fetchval = AsyncMock(side_effect=[None, 3])
        conn.close = AsyncMock()
        mock_connect.return_value = conn

        # Act
        resp = client.post(f"/staging/{session_id}/approve")

        # Assert
        assert resp.status_code == 200
        assert resp.json() == {"session_id": session_id, "approved": 3}


class TestReject:
    @patch("app.api.staging.asyncpg.connect", new_callable=AsyncMock)
    def test_reject_single_draft_returns_rejected(self, mock_connect):
        # Arrange
        staging_id = str(uuid.uuid4())
        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value=1)
        conn.execute = AsyncMock(return_value="UPDATE 1")
        conn.close = AsyncMock()
        mock_connect.return_value = conn

        # Act
        resp = client.post(f"/staging/{staging_id}/reject")

        # Assert
        assert resp.status_code == 200
        assert resp.json() == {"id": staging_id, "state": "REJECTED"}

    @patch("app.api.staging.asyncpg.connect", new_callable=AsyncMock)
    def test_reject_single_non_draft_returns_400(self, mock_connect):
        # Arrange
        staging_id = str(uuid.uuid4())
        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value=1)
        conn.execute = AsyncMock(return_value="UPDATE 0")
        conn.close = AsyncMock()
        mock_connect.return_value = conn

        # Act
        resp = client.post(f"/staging/{staging_id}/reject")

        # Assert
        assert resp.status_code == 400

    @patch("app.api.staging.asyncpg.connect", new_callable=AsyncMock)
    def test_reject_session_bulk_returns_rejected_count(self, mock_connect):
        # Arrange
        session_id = str(uuid.uuid4())
        conn = AsyncMock()
        conn.fetchval = AsyncMock(side_effect=[None, 2])
        conn.close = AsyncMock()
        mock_connect.return_value = conn

        # Act
        resp = client.post(f"/staging/{session_id}/reject")

        # Assert
        assert resp.status_code == 200
        assert resp.json() == {"session_id": session_id, "rejected": 2}


class TestCommit:
    @patch("app.api.staging.write_graph_task")
    def test_commit_triggers_write_graph_with_path_param(self, mock_task):
        # Arrange
        mock_task.apply_async = MagicMock()
        session_id = str(uuid.uuid4())

        # Act
        resp = client.post(f"/staging/{session_id}/commit")

        # Assert
        assert resp.status_code == 202
        assert resp.json() == {"session_id": session_id, "status": "write_graph_triggered"}
        mock_task.apply_async.assert_called_once_with(args=[session_id])


class TestDiff:
    @patch("app.api.staging.asyncpg.connect", new_callable=AsyncMock)
    def test_diff_returns_state_counts_summary(self, mock_connect):
        # Arrange
        session_id = str(uuid.uuid4())
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[
            {"state": "DRAFT", "cnt": 2},
            {"state": "APPROVED", "cnt": 1},
        ])
        conn.close = AsyncMock()
        mock_connect.return_value = conn

        # Act
        resp = client.get(f"/staging/{session_id}/diff")

        # Assert
        assert resp.status_code == 200
        assert resp.json() == {"draft": 2, "approved": 1, "committed": 0}

    @patch("app.api.staging.asyncpg.connect", new_callable=AsyncMock)
    def test_diff_returns_zero_counts_for_unknown_session(self, mock_connect):
        # Arrange
        session_id = str(uuid.uuid4())
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[])
        conn.close = AsyncMock()
        mock_connect.return_value = conn

        # Act
        resp = client.get(f"/staging/{session_id}/diff")

        # Assert
        assert resp.status_code == 200
        assert resp.json() == {"draft": 0, "approved": 0, "committed": 0}
