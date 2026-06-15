"""webhook_adapter 단위테스트 — 이벤트 필터 로직 검증."""
from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import patch

import pytest

from src.adapters.webhook_adapter import app

client = app.test_client()


def _payload(action: str) -> bytes:
    data = {
        "action": action,
        "repository": {"full_name": "owner/repo"},
        "pull_request": {"number": 1, "user": {"login": "tester"}},
    }
    return json.dumps(data).encode()


def _post(action: str, secret: str = "") -> object:
    body = _payload(action)
    headers = {"X-GitHub-Event": "pull_request"}
    if secret:
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        headers["X-Hub-Signature-256"] = sig
    # WEBHOOK_SECRET 을 빈 문자열로 patch → 서명 검증 skip
    with patch("src.adapters.webhook_adapter.WEBHOOK_SECRET", ""), \
         patch("src.adapters.webhook_adapter.threading.Thread") as mock_thread:
        mock_thread.return_value.start = lambda: None
        return client.post("/webhook", data=body, content_type="application/json",
                           headers=headers), mock_thread


# ── opened / synchronize → 처리됨 (202) ─────────────────────────────────────

def test_opened_accepted():
    resp, mock_thread = _post("opened")
    assert resp.status_code == 202
    assert resp.get_json()["status"] == "accepted"
    mock_thread.assert_called_once()


def test_synchronize_accepted():
    resp, mock_thread = _post("synchronize")
    assert resp.status_code == 202
    assert resp.get_json()["status"] == "accepted"
    mock_thread.assert_called_once()


# ── reopened / closed → 무시됨 (200) ─────────────────────────────────────────

def test_reopened_ignored():
    resp, mock_thread = _post("reopened")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ignored"
    mock_thread.assert_not_called()


def test_closed_ignored():
    resp, mock_thread = _post("closed")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ignored"
    mock_thread.assert_not_called()


# ── 비-PR 이벤트 → 무시됨 (200) ──────────────────────────────────────────────

def test_push_event_ignored():
    body = json.dumps({"ref": "refs/heads/main"}).encode()
    with patch("src.adapters.webhook_adapter.WEBHOOK_SECRET", ""), \
         patch("src.adapters.webhook_adapter.threading.Thread") as mock_thread:
        mock_thread.return_value.start = lambda: None
        resp = client.post("/webhook", data=body, content_type="application/json",
                           headers={"X-GitHub-Event": "push"})
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ignored"


# ── HMAC 서명 실패 → 401 ──────────────────────────────────────────────────────

def test_invalid_signature_rejected():
    body = _payload("opened")
    with patch("src.adapters.webhook_adapter.WEBHOOK_SECRET", "real-secret"):
        resp = client.post("/webhook", data=body, content_type="application/json",
                           headers={"X-GitHub-Event": "pull_request",
                                    "X-Hub-Signature-256": "sha256=badsig"})
    assert resp.status_code == 401
