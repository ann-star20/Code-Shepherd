"""webhook.py 테스트 — 서명검증·action 필터·diff fetch·오케스트레이션 연결.

실제 GitHub/도구/네트워크 없이 통과해야 한다(fetch_diff·analyze를 Mock).
"""

import hashlib
import hmac
import json

import pytest
from httpx import ASGITransport, AsyncClient

from app import orchestrator, webhook
from app.main import app
from app.webhook import verify_signature
from shared.contracts import IssueItem, IssueSummary

PY_DIFF = """diff --git a/src/db.py b/src/db.py
--- a/src/db.py
+++ b/src/db.py
@@ -0,0 +1,2 @@
+def add(a, b):
+    return a + b
"""

PR_PAYLOAD = {
    "action": "opened",
    "number": 42,
    "pull_request": {
        "id": 9001,
        "number": 42,
        "diff_url": "https://github.com/o/r/pull/42.diff",
        "user": {"login": "alice"},
    },
    "repository": {"full_name": "o/r"},
}


def _fake_analyze(_diff, agent):
    return [IssueItem(severity="Major", message="x", rule_id="SA-X")], IssueSummary(major=1), 5


async def _fake_fetch_diff(_url):
    return PY_DIFF


async def _no_m4(_req):
    return None


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# ── 서명 검증 단위 ──

def test_verify_signature_skips_when_no_secret():
    assert verify_signature(None, b"body", None) is True


def test_verify_signature_accepts_valid():
    body = b"hello"
    sig = _sign("s3cr3t", body)
    assert verify_signature("s3cr3t", body, sig) is True


def test_verify_signature_rejects_invalid():
    assert verify_signature("s3cr3t", b"hello", "sha256=deadbeef") is False


def test_verify_signature_rejects_missing_header():
    assert verify_signature("s3cr3t", b"hello", None) is False


# ── 엔드포인트 ──

@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    monkeypatch.setattr(orchestrator, "analyze", _fake_analyze)
    monkeypatch.setattr(orchestrator.m4_client, "evaluate", _no_m4)
    monkeypatch.setattr(webhook, "fetch_diff", _fake_fetch_diff)


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_webhook_runs_orchestration(client, monkeypatch):
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)
    resp = await client.post(
        "/webhook/github",
        content=json.dumps(PR_PAYLOAD),
        headers={"X-GitHub-Event": "pull_request"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["pr_id"] == "9001"
    assert data["ran_agents"] == ["static_analysis", "security_scan"]


@pytest.mark.asyncio
async def test_webhook_rejects_bad_signature(client, monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "topsecret")
    resp = await client.post(
        "/webhook/github",
        content=json.dumps(PR_PAYLOAD),
        headers={"X-GitHub-Event": "pull_request", "X-Hub-Signature-256": "sha256=bad"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_webhook_accepts_valid_signature(client, monkeypatch):
    secret = "topsecret"
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", secret)
    body = json.dumps(PR_PAYLOAD)
    resp = await client.post(
        "/webhook/github",
        content=body,
        headers={
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": _sign(secret, body.encode()),
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


@pytest.mark.asyncio
async def test_webhook_ignores_non_pr_event(client, monkeypatch):
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)
    resp = await client.post(
        "/webhook/github",
        content=json.dumps({"zen": "ping"}),
        headers={"X-GitHub-Event": "ping"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "skip"


@pytest.mark.asyncio
async def test_webhook_ignores_unhandled_action(client, monkeypatch):
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)
    payload = {**PR_PAYLOAD, "action": "closed"}
    resp = await client.post(
        "/webhook/github",
        content=json.dumps(payload),
        headers={"X-GitHub-Event": "pull_request"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "skip"
    assert "closed" in resp.json()["skip_reason"]
