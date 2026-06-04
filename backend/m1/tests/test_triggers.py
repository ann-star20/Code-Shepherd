"""TDD: HMAC 서명 검증, 라우팅 디스패치, 트레이스 로그 필드."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
import respx
from httpx import Response


SECRET = "test-webhook-secret"


def _sign(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


PR_PAYLOAD = json.dumps({
    "action": "opened",
    "number": 42,
    "pull_request": {"diff_url": ""},
    "sender": {"login": "octocat"},
    "repository": {"full_name": "org/repo"},
}).encode()


STUB_M2_RESPONSE = {
    "task_id": "t1",
    "agent": "static_analysis",
    "issues": [],
    "summary": {"critical": 0, "major": 0, "minor": 0},
    "execution_ms": 10,
}
STUB_M3_RESPONSE = {
    "task_id": "t1",
    "agent": "test_verification",
    "issues": [],
    "summary": {"critical": 0, "major": 0, "minor": 0},
    "execution_ms": 10,
}
STUB_M4_RESPONSE = {
    "task_id": "t1",
    "pr_id": "42",
    "verdict": "lgtm",
    "comment_body": "LGTM",
    "execution_ms": 10,
}


# ---------------------------------------------------------------------------
# HMAC 서명 검증
# ---------------------------------------------------------------------------

def _mock_api_core_ingest(mock):
    mock.post("http://api-core:8000/internal/pr-ingest").mock(
        return_value=Response(
            200,
            json={
                "pr_id": "00000000-0000-0000-0000-000000000001",
                "team_id": "00000000-0000-0000-0000-000000000002",
                "created": True,
                "status": "ingested",
            },
        )
    )


def _mock_all_modules(mock):
    _mock_api_core_ingest(mock)
    mock.post("http://m2:8003/analyze/static").mock(return_value=Response(200, json=STUB_M2_RESPONSE))
    mock.post("http://m2:8003/analyze/security").mock(return_value=Response(200, json={**STUB_M2_RESPONSE, "agent": "security_scan"}))
    mock.post("http://m3:8004/verify/tests").mock(return_value=Response(200, json=STUB_M3_RESPONSE))
    mock.post("http://m3:8004/analyze/performance").mock(return_value=Response(200, json={**STUB_M3_RESPONSE, "agent": "performance"}))
    mock.post("http://m4:8005/evaluate").mock(return_value=Response(200, json=STUB_M4_RESPONSE))


@pytest.mark.asyncio
async def test_valid_signature_accepted(client):
    """유효한 HMAC 서명 → 200 (모듈 호출은 respx로 모킹)."""
    with respx.mock as mock:
        _mock_all_modules(mock)
        sig = _sign(PR_PAYLOAD)
        resp = await client.post(
            "/triggers/pr",
            content=PR_PAYLOAD,
            headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "task_id" in data
    assert "trace_id" in data


@pytest.mark.asyncio
async def test_invalid_signature_rejected(client):
    """잘못된 HMAC 서명 → 401."""
    resp = await client.post(
        "/triggers/pr",
        content=PR_PAYLOAD,
        headers={"X-Hub-Signature-256": "sha256=badhash", "Content-Type": "application/json"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_missing_signature_rejected(client):
    """서명 없음 → 401."""
    resp = await client.post(
        "/triggers/pr",
        content=PR_PAYLOAD,
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_pr_trigger_skipped_when_ingest_404(client):
    """등록되지 않은 repo → ingest 404 → 스킵(모듈 미호출)."""
    with respx.mock as mock:
        mock.post("http://api-core:8000/internal/pr-ingest").mock(
            return_value=Response(404, json={"detail": "No team registered"})
        )
        sig = _sign(PR_PAYLOAD)
        resp = await client.post(
            "/triggers/pr",
            content=PR_PAYLOAD,
            headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "skipped"


# ---------------------------------------------------------------------------
# 라우팅 디스패치 — PR 트리거는 m2·m3·m4 호출
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pr_trigger_calls_api_core_ingest(client):
    """PR 트리거 수신 시 api-core pr-ingest 호출."""
    with respx.mock as mock:
        ingest = mock.post("http://api-core:8000/internal/pr-ingest").mock(
            return_value=Response(200, json={"status": "ingested", "created": True})
        )
        _mock_all_modules(mock)
        sig = _sign(PR_PAYLOAD)
        resp = await client.post(
            "/triggers/pr",
            content=PR_PAYLOAD,
            headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"},
        )
    assert resp.status_code == 200
    assert ingest.called


@pytest.mark.asyncio
async def test_pr_trigger_calls_m2_m3_m4(client):
    """PR 트리거 수신 시 m2(static+security), m3(tests+perf), m4(evaluate) 호출."""
    with respx.mock as mock:
        _mock_api_core_ingest(mock)
        m2_static = mock.post("http://m2:8003/analyze/static").mock(
            return_value=Response(200, json=STUB_M2_RESPONSE)
        )
        m2_security = mock.post("http://m2:8003/analyze/security").mock(
            return_value=Response(200, json={**STUB_M2_RESPONSE, "agent": "security_scan"})
        )
        m3_tests = mock.post("http://m3:8004/verify/tests").mock(
            return_value=Response(200, json=STUB_M3_RESPONSE)
        )
        m3_perf = mock.post("http://m3:8004/analyze/performance").mock(
            return_value=Response(200, json={**STUB_M3_RESPONSE, "agent": "performance"})
        )
        m4_eval = mock.post("http://m4:8005/evaluate").mock(
            return_value=Response(200, json=STUB_M4_RESPONSE)
        )

        sig = _sign(PR_PAYLOAD)
        resp = await client.post(
            "/triggers/pr",
            content=PR_PAYLOAD,
            headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"},
        )

    assert resp.status_code == 200
    assert m2_static.called
    assert m2_security.called
    assert m3_tests.called
    assert m3_perf.called
    assert m4_eval.called


@pytest.mark.asyncio
async def test_document_trigger_calls_m0(client):
    """문서 트리거 수신 시 m0(ingest) 호출."""
    with respx.mock as mock:
        m0_ingest = mock.post("http://m0:8002/ingest").mock(
            return_value=Response(
                200,
                json={"task_id": "t0", "status": "accepted", "message": "Stub"},
            )
        )
        resp = await client.post(
            "/triggers/document",
            json={"doc_id": "doc-123", "source": "upload"},
            headers={"Content-Type": "application/json"},
        )

    assert resp.status_code == 200
    assert m0_ingest.called


# ---------------------------------------------------------------------------
# 트레이스 로그 필드 (응답에 trace_id 포함 확인)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pr_trigger_response_has_trace_id(client):
    with respx.mock as mock:
        _mock_all_modules(mock)
        sig = _sign(PR_PAYLOAD)
        resp = await client.post(
            "/triggers/pr",
            content=PR_PAYLOAD,
            headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"},
        )

    data = resp.json()
    assert "trace_id" in data
    assert data["trace_id"]  # 비어있지 않음


# ---------------------------------------------------------------------------
# 헬스체크
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
