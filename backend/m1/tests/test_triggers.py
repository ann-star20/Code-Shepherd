"""TDD: HMAC 서명 검증 + 즉시 202 접수 + 백그라운드 분석 체인.

GitHub 웹훅은 10초 안에 응답을 기대한다. /triggers/pr 는 서명 검증 직후 즉시 202 를 반환하고,
무거운 분석 체인(ingest → diff → m2/m3 → m3 /review)은 백그라운드에서 돈다.
(테스트 함정) httpx ASGITransport 는 응답 후 백그라운드까지 끝낸 뒤 반환하므로,
respx 의 .called 단언은 실서버가 비동기여도 테스트에선 그대로 유효하다.
"""

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


async def _post(client, body: bytes, *, sign: bool = True, sig: str | None = None):
    headers = {"Content-Type": "application/json"}
    if sign:
        headers["X-Hub-Signature-256"] = sig or _sign(body)
    elif sig is not None:
        headers["X-Hub-Signature-256"] = sig
    return await client.post("/triggers/pr", content=body, headers=headers)


# ---------------------------------------------------------------------------
# 즉시 202 접수 (핵심 새 동작)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_valid_signature_returns_202_accepted(client):
    """유효한 HMAC 서명 → 즉시 202 'accepted' + trace_id (분석은 기다리지 않음)."""
    with respx.mock as mock:
        _mock_all_modules(mock)
        resp = await _post(client, PR_PAYLOAD)
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "accepted"
    assert data["trace_id"]


@pytest.mark.asyncio
async def test_background_chain_calls_m2_m3_review(client):
    """202 반환 후 백그라운드에서 m2(static+security)·m3(tests+perf)·m3(review)가 실제 호출된다."""
    with respx.mock as mock:
        _mock_api_core_ingest(mock)
        m2_static = mock.post("http://m2:8003/analyze/static").mock(return_value=Response(200, json=STUB_M2_RESPONSE))
        m2_security = mock.post("http://m2:8003/analyze/security").mock(return_value=Response(200, json={**STUB_M2_RESPONSE, "agent": "security_scan"}))
        m3_tests = mock.post("http://m3:8004/verify/tests").mock(return_value=Response(200, json=STUB_M3_RESPONSE))
        m3_perf = mock.post("http://m3:8004/analyze/performance").mock(return_value=Response(200, json={**STUB_M3_RESPONSE, "agent": "performance"}))
        m3_review = mock.post("http://m3:8004/review").mock(return_value=Response(200, json=STUB_M3_REVIEW_RESPONSE))

        resp = await _post(client, PR_PAYLOAD)

    assert resp.status_code == 202
    assert m2_static.called
    assert m2_security.called
    assert m3_tests.called
    assert m3_perf.called
    assert m3_review.called


@pytest.mark.asyncio
async def test_pr_trigger_response_has_trace_id(client):
    """202 응답에 trace_id 가 들어있다(로그 상관관계용)."""
    with respx.mock as mock:
        _mock_all_modules(mock)
        resp = await _post(client, PR_PAYLOAD)
    assert resp.status_code == 202
    assert resp.json()["trace_id"]


# ---------------------------------------------------------------------------
# HMAC 서명 검증 — 응답 전에 그대로 (잘못된/없는 서명 → 401)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_invalid_signature_rejected(client):
    """잘못된 HMAC 서명 → 401 (백그라운드 스케줄 안 함)."""
    with respx.mock as mock:
        ingest = mock.post("http://api-core:8000/internal/pr-ingest").mock(
            return_value=Response(200, json={"status": "ingested"})
        )
        resp = await _post(client, PR_PAYLOAD, sign=False, sig="sha256=badhash")
    assert resp.status_code == 401
    assert not ingest.called  # 서명 실패 → 백그라운드 체인 시작 안 됨


@pytest.mark.asyncio
async def test_missing_signature_rejected(client):
    """서명 헤더 없음 → 401."""
    resp = await _post(client, PR_PAYLOAD, sign=False)
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 백그라운드는 예외를 raise 하지 않고 정직하게 로그/스킵으로 처리
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unregistered_repo_ingest_404_skips_modules(client):
    """미등록 레포 → ingest 404 → 백그라운드 스킵(모듈 미호출). 응답은 그대로 202."""
    with respx.mock(assert_all_called=False) as mock:
        mock.post("http://api-core:8000/internal/pr-ingest").mock(
            return_value=Response(404, json={"detail": "No team registered"})
        )
        m2_static = mock.post("http://m2:8003/analyze/static").mock(return_value=Response(200, json=STUB_M2_RESPONSE))
        m3_review = mock.post("http://m3:8004/review").mock(return_value=Response(200, json=STUB_M3_REVIEW_RESPONSE))

        resp = await _post(client, PR_PAYLOAD)

    assert resp.status_code == 202        # 접수는 정상
    assert not m2_static.called           # 미등록 → 분석 모듈 미호출
    assert not m3_review.called


@pytest.mark.asyncio
async def test_module_failure_does_not_raise(client):
    """백그라운드 모듈 실패(예: m2 500)는 raise 하지 않고 로그만 — 응답은 202 로 정상 종료."""
    with respx.mock(assert_all_called=False) as mock:
        _mock_api_core_ingest(mock)
        mock.post("http://m2:8003/analyze/static").mock(return_value=Response(500, json={"detail": "boom"}))
        # 나머지는 호출 안 될 수 있음(첫 모듈에서 실패) — assert_all_called=False

        resp = await _post(client, PR_PAYLOAD)

    # 백그라운드가 예외를 삼켰으므로 ASGITransport 가 끝까지 돌고도 202 로 정상 반환
    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_invalid_json_body_still_accepts(client):
    """본문이 JSON 이 아니어도(서명만 유효) 202 접수 — 백그라운드에서 파싱 실패 로그 후 스킵."""
    bad_body = b"this is not json {{{"
    with respx.mock(assert_all_called=False) as mock:
        ingest = mock.post("http://api-core:8000/internal/pr-ingest").mock(
            return_value=Response(200, json={"status": "ingested"})
        )
        resp = await _post(client, bad_body)  # 서명은 bad_body 기준으로 유효
    assert resp.status_code == 202
    assert not ingest.called  # 파싱 실패 → 체인 진입 안 함


@pytest.mark.asyncio
async def test_missing_repository_skips_no_modules(client):
    """repository.full_name 누락 → 백그라운드 스킵(ingest/모듈 미호출). 응답은 202."""
    payload = json.dumps({
        "action": "opened",
        "number": 42,
        "pull_request": {"diff_url": ""},
        "sender": {"login": "octocat"},
        # repository 없음
    }).encode()
    with respx.mock(assert_all_called=False) as mock:
        ingest = mock.post("http://api-core:8000/internal/pr-ingest").mock(
            return_value=Response(200, json={"status": "ingested"})
        )
        resp = await _post(client, payload)
    assert resp.status_code == 202
    assert not ingest.called


# ---------------------------------------------------------------------------
# PR 액션 필터 — 분석 대상 액션만 처리(closed 등은 스킵 → 코멘트 중복 방지)
# 회귀: 데모 Close→Reopen 시 closed+reopened 두 신호에 모두 반응 → 코멘트 2개 버그.
# ---------------------------------------------------------------------------

def _pr_payload(action: str) -> bytes:
    return json.dumps({
        "action": action,
        "number": 42,
        "pull_request": {"diff_url": ""},
        "sender": {"login": "octocat"},
        "repository": {"full_name": "org/repo"},
    }).encode()


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["closed", "edited", "labeled", "assigned", "review_requested"])
async def test_non_analyzable_action_skips_no_modules(client, action):
    """closed/edited/labeled 등 비분석 PR 액션 → 202 접수만, ingest·분석·리뷰 미호출."""
    with respx.mock(assert_all_called=False) as mock:
        ingest = mock.post("http://api-core:8000/internal/pr-ingest").mock(
            return_value=Response(200, json={"status": "ingested"})
        )
        m3_review = mock.post("http://m3:8004/review").mock(
            return_value=Response(200, json=STUB_M3_REVIEW_RESPONSE)
        )
        resp = await _post(client, _pr_payload(action))
    assert resp.status_code == 202
    assert not ingest.called      # 비분석 이벤트 → 체인 진입 안 함
    assert not m3_review.called    # → 코멘트도 안 달림(중복 방지)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["opened", "reopened", "synchronize"])
async def test_analyzable_action_runs_review(client, action):
    """opened/reopened/synchronize → 정상 분석·리뷰(데모 Reopen 재발사 유지)."""
    with respx.mock as mock:
        _mock_api_core_ingest(mock)
        mock.post("http://m2:8003/analyze/static").mock(return_value=Response(200, json=STUB_M2_RESPONSE))
        mock.post("http://m2:8003/analyze/security").mock(return_value=Response(200, json={**STUB_M2_RESPONSE, "agent": "security_scan"}))
        mock.post("http://m3:8004/verify/tests").mock(return_value=Response(200, json=STUB_M3_RESPONSE))
        mock.post("http://m3:8004/analyze/performance").mock(return_value=Response(200, json={**STUB_M3_RESPONSE, "agent": "performance"}))
        m3_review = mock.post("http://m3:8004/review").mock(return_value=Response(200, json=STUB_M3_REVIEW_RESPONSE))
        resp = await _post(client, _pr_payload(action))
    assert resp.status_code == 202
    assert m3_review.called


# ---------------------------------------------------------------------------
# 라우팅/디스패치 — 백그라운드에서 api-core ingest 호출
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_background_calls_api_core_ingest(client):
    """백그라운드에서 api-core pr-ingest 가 호출된다."""
    with respx.mock as mock:
        ingest = mock.post("http://api-core:8000/internal/pr-ingest").mock(
            return_value=Response(200, json={"status": "ingested", "created": True})
        )
        _mock_all_modules(mock)
        resp = await _post(client, PR_PAYLOAD)
    assert resp.status_code == 202
    assert ingest.called


# ---------------------------------------------------------------------------
# 진짜 값 채워 보내기 — diff 본문 fetch + repo 좌표 (백그라운드에서 수행)
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
async def test_background_fetches_diff_body_and_fills_repo_fields(client):
    """diff_url 을 본문으로 fetch 해 m2·m3 둘 다 동일 본문으로 보내고,
    m3 에는 clone_url/commit_sha 까지 채워 보낸다(백그라운드에서 수행)."""
    with respx.mock as mock:
        _mock_api_core_ingest(mock)
        diff_route = mock.get(DIFF_URL).mock(return_value=Response(200, text=DIFF_BODY))
        m2_static = mock.post("http://m2:8003/analyze/static").mock(return_value=Response(200, json=STUB_M2_RESPONSE))
        mock.post("http://m2:8003/analyze/security").mock(return_value=Response(200, json={**STUB_M2_RESPONSE, "agent": "security_scan"}))
        m3_tests = mock.post("http://m3:8004/verify/tests").mock(return_value=Response(200, json=STUB_M3_RESPONSE))
        m3_perf = mock.post("http://m3:8004/analyze/performance").mock(return_value=Response(200, json={**STUB_M3_RESPONSE, "agent": "performance"}))
        mock.post("http://m3:8004/review").mock(return_value=Response(200, json=STUB_M3_REVIEW_RESPONSE))

        resp = await _post(client, PR_PAYLOAD_FULL)

    assert resp.status_code == 202
    assert diff_route.called

    m3_body = json.loads(m3_tests.calls.last.request.content)
    assert m3_body["pr_diff"] == DIFF_BODY
    assert not m3_body["pr_diff"].startswith("http")
    assert m3_body["clone_url"] == CLONE_URL
    assert m3_body["commit_sha"] == HEAD_SHA

    m3_perf_body = json.loads(m3_perf.calls.last.request.content)
    assert m3_perf_body["clone_url"] == CLONE_URL
    assert m3_perf_body["commit_sha"] == HEAD_SHA

    m2_body = json.loads(m2_static.calls.last.request.content)
    assert m2_body["pr_diff"] == DIFF_BODY


@pytest.mark.asyncio
async def test_background_clone_url_falls_back_to_repository(client):
    """head.repo.clone_url 이 없으면 repository.clone_url 로 폴백한다(백그라운드)."""
    payload = json.dumps({
        "action": "opened",
        "number": 4,
        "pull_request": {
            "number": 4,
            "diff_url": "",
            "user": {"login": "junior_dev_01"},
            "head": {"sha": HEAD_SHA},
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

        resp = await _post(client, payload)

    assert resp.status_code == 202
    m3_body = json.loads(m3_tests.calls.last.request.content)
    assert m3_body["clone_url"] == CLONE_URL
    assert m3_body["commit_sha"] == HEAD_SHA
    assert m3_body["pr_diff"] == ""


@pytest.mark.asyncio
async def test_background_calls_m3_review_with_four_results_not_m4(client):
    """판정·코멘트는 m3 소유 — 백그라운드가 m3 /review 를 4결과+repository+pr_number 로 호출하고
    m4 /evaluate 는 호출하지 않는다."""
    with respx.mock(assert_all_called=False) as mock:
        _mock_api_core_ingest(mock)
        mock.post("http://m2:8003/analyze/static").mock(return_value=Response(200, json=STUB_M2_RESPONSE))
        mock.post("http://m2:8003/analyze/security").mock(return_value=Response(200, json={**STUB_M2_RESPONSE, "agent": "security_scan"}))
        mock.post("http://m3:8004/verify/tests").mock(return_value=Response(200, json=STUB_M3_RESPONSE))
        mock.post("http://m3:8004/analyze/performance").mock(return_value=Response(200, json={**STUB_M3_RESPONSE, "agent": "performance"}))
        m3_review = mock.post("http://m3:8004/review").mock(return_value=Response(200, json=STUB_M3_REVIEW_RESPONSE))
        m4_eval = mock.post("http://m4:8005/evaluate").mock(return_value=Response(200, json=STUB_M4_RESPONSE))

        resp = await _post(client, PR_PAYLOAD)

    assert resp.status_code == 202
    assert m3_review.called
    assert not m4_eval.called

    body = json.loads(m3_review.calls.last.request.content)
    assert body["repository"] == "org/repo"
    assert body["pr_number"] == 42
    assert body["static_analysis"]["agent"] == "static_analysis"
    assert body["security_scan"]["agent"] == "security_scan"
    assert body["test_verification"]["agent"] == "test_verification"
    assert body["performance"]["agent"] == "performance"


# ---------------------------------------------------------------------------
# 문서 트리거 / 헬스 (이번 변경 범위 밖 — 그대로 유지)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_document_trigger_calls_m0(client):
    """문서 트리거 수신 시 m0(ingest) 호출."""
    with respx.mock as mock:
        m0_ingest = mock.post("http://m0:8002/ingest").mock(
            return_value=Response(200, json={"task_id": "t0", "status": "accepted", "message": "Stub"})
        )
        resp = await client.post(
            "/triggers/document",
            json={"doc_id": "doc-123", "source": "upload"},
            headers={"Content-Type": "application/json"},
        )
    assert resp.status_code == 200
    assert m0_ingest.called


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
