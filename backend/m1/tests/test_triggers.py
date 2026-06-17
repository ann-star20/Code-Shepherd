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
STUB_M3_REVIEW_RESPONSE = {
    "task_id": "t1",
    "pr_id": "42",
    "verdict": "lgtm",
    "comment_posted": False,
    "comment_url": None,
    "persisted": True,
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
    mock.post("http://m3:8004/review").mock(return_value=Response(200, json=STUB_M3_REVIEW_RESPONSE))


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
async def test_pr_trigger_calls_m2_m3_review(client):
    """PR 트리거 수신 시 m2(static+security), m3(tests+perf), m3(review) 호출."""
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
        m3_review = mock.post("http://m3:8004/review").mock(
            return_value=Response(200, json=STUB_M3_REVIEW_RESPONSE)
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
    assert m3_review.called


# ---------------------------------------------------------------------------
# 수정① — m1 이 m3/m2 로 "진짜 값"을 채워 보낸다
#   · pr_diff = diff_url 을 fetch 한 본문(URL 그대로 X)
#   · clone_url = head.repo.clone_url (없으면 repository.clone_url)
#   · commit_sha = head.sha
# ---------------------------------------------------------------------------

DIFF_URL = "https://github.com/kskt1234-netizen/-dev3-demo/pull/4.diff"
DIFF_BODY = "diff --git a/app.py b/app.py\n@@ -1 +1 @@\n-old\n+new\n"
CLONE_URL = "https://github.com/kskt1234-netizen/-dev3-demo.git"
HEAD_SHA = "27f5c96142260206ce714da1294aefbbddb0f4f6"

PR_PAYLOAD_FULL = json.dumps({
    "action": "opened",
    "number": 4,
    "pull_request": {
        "number": 4,
        "diff_url": DIFF_URL,
        "user": {"login": "junior_dev_01"},
        "head": {"sha": HEAD_SHA, "repo": {"clone_url": CLONE_URL}},
    },
    "sender": {"login": "junior_dev_01"},
    "repository": {"full_name": "kskt1234-netizen/-dev3-demo", "clone_url": CLONE_URL},
}).encode()


@pytest.mark.asyncio
async def test_pr_trigger_fetches_diff_body_and_fills_repo_fields(client):
    """diff_url 을 본문으로 fetch 해 m2·m3 둘 다 동일 본문으로 보내고,
    m3 에는 clone_url/commit_sha 까지 채워 보낸다(라우팅이 아니라 실 분석이 가능하게)."""
    with respx.mock as mock:
        _mock_api_core_ingest(mock)
        diff_route = mock.get(DIFF_URL).mock(return_value=Response(200, text=DIFF_BODY))
        m2_static = mock.post("http://m2:8003/analyze/static").mock(
            return_value=Response(200, json=STUB_M2_RESPONSE)
        )
        mock.post("http://m2:8003/analyze/security").mock(
            return_value=Response(200, json={**STUB_M2_RESPONSE, "agent": "security_scan"})
        )
        m3_tests = mock.post("http://m3:8004/verify/tests").mock(
            return_value=Response(200, json=STUB_M3_RESPONSE)
        )
        m3_perf = mock.post("http://m3:8004/analyze/performance").mock(
            return_value=Response(200, json={**STUB_M3_RESPONSE, "agent": "performance"})
        )
        mock.post("http://m3:8004/review").mock(return_value=Response(200, json=STUB_M3_REVIEW_RESPONSE))

        sig = _sign(PR_PAYLOAD_FULL)
        resp = await client.post(
            "/triggers/pr",
            content=PR_PAYLOAD_FULL,
            headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"},
        )

    assert resp.status_code == 200
    assert diff_route.called  # diff_url 을 실제로 fetch 했는가

    # m3(verify/tests) 가 받은 본문 검증
    m3_body = json.loads(m3_tests.calls.last.request.content)
    assert m3_body["pr_diff"] == DIFF_BODY          # URL 이 아니라 'diff --git' 본문
    assert not m3_body["pr_diff"].startswith("http")
    assert m3_body["clone_url"] == CLONE_URL
    assert m3_body["commit_sha"] == HEAD_SHA

    # m3(analyze/performance) 도 동일 repo 좌표
    m3_perf_body = json.loads(m3_perf.calls.last.request.content)
    assert m3_perf_body["clone_url"] == CLONE_URL
    assert m3_perf_body["commit_sha"] == HEAD_SHA

    # m2 로 가는 pr_diff 도 동일 본문으로 통일
    m2_body = json.loads(m2_static.calls.last.request.content)
    assert m2_body["pr_diff"] == DIFF_BODY


@pytest.mark.asyncio
async def test_pr_trigger_clone_url_falls_back_to_repository(client):
    """head.repo.clone_url 이 없으면 repository.clone_url 로 폴백한다."""
    payload = json.dumps({
        "action": "opened",
        "number": 4,
        "pull_request": {
            "number": 4,
            "diff_url": "",  # diff 없음 → fetch 생략, 빈 본문(정직)
            "user": {"login": "junior_dev_01"},
            "head": {"sha": HEAD_SHA},  # head.repo 없음
        },
        "sender": {"login": "junior_dev_01"},
        "repository": {"full_name": "kskt1234-netizen/-dev3-demo", "clone_url": CLONE_URL},
    }).encode()

    with respx.mock as mock:
        _mock_api_core_ingest(mock)
        mock.post("http://m2:8003/analyze/static").mock(return_value=Response(200, json=STUB_M2_RESPONSE))
        mock.post("http://m2:8003/analyze/security").mock(return_value=Response(200, json={**STUB_M2_RESPONSE, "agent": "security_scan"}))
        m3_tests = mock.post("http://m3:8004/verify/tests").mock(return_value=Response(200, json=STUB_M3_RESPONSE))
        mock.post("http://m3:8004/analyze/performance").mock(return_value=Response(200, json={**STUB_M3_RESPONSE, "agent": "performance"}))
        mock.post("http://m3:8004/review").mock(return_value=Response(200, json=STUB_M3_REVIEW_RESPONSE))

        sig = _sign(payload)
        resp = await client.post(
            "/triggers/pr",
            content=payload,
            headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"},
        )
    assert resp.status_code == 200
    m3_body = json.loads(m3_tests.calls.last.request.content)
    assert m3_body["clone_url"] == CLONE_URL   # repository.clone_url 폴백
    assert m3_body["commit_sha"] == HEAD_SHA
    assert m3_body["pr_diff"] == ""            # diff_url 비어있음 → 빈 본문(가짜 없음)


@pytest.mark.asyncio
async def test_pr_trigger_calls_m3_review_with_four_results_not_m4(client):
    """판정·코멘트는 m3 소유 — PR 트리거가 m3 /review 를 4결과+repository+pr_number 로
    호출하고, m4 /evaluate 는 호출하지 않는다."""
    with respx.mock(assert_all_called=False) as mock:
        _mock_api_core_ingest(mock)
        mock.post("http://m2:8003/analyze/static").mock(
            return_value=Response(200, json=STUB_M2_RESPONSE)
        )
        mock.post("http://m2:8003/analyze/security").mock(
            return_value=Response(200, json={**STUB_M2_RESPONSE, "agent": "security_scan"})
        )
        mock.post("http://m3:8004/verify/tests").mock(
            return_value=Response(200, json=STUB_M3_RESPONSE)
        )
        mock.post("http://m3:8004/analyze/performance").mock(
            return_value=Response(200, json={**STUB_M3_RESPONSE, "agent": "performance"})
        )
        m3_review = mock.post("http://m3:8004/review").mock(
            return_value=Response(200, json=STUB_M3_REVIEW_RESPONSE)
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
    assert m3_review.called          # m3 /review 호출됨
    assert not m4_eval.called        # m4 /evaluate 미호출 (코멘트·판정은 m3 소유)

    body = json.loads(m3_review.calls.last.request.content)
    # 4결과 동형 + repository + pr_number 를 채워 보냈는가
    assert body["repository"] == "org/repo"
    assert body["pr_number"] == 42
    assert body["static_analysis"]["agent"] == "static_analysis"
    assert body["security_scan"]["agent"] == "security_scan"
    assert body["test_verification"]["agent"] == "test_verification"
    assert body["performance"]["agent"] == "performance"


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
