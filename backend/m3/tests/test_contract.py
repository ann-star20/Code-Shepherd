"""계약 테스트 — m3 엔드포인트."""

from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

import app.main as appmain
from app.main import app

VERIFY_PAYLOAD = {
    "task_id": "t-002",
    "pr_id": "43",
    "pr_diff": "diff --git ...",
}

# M1 이 보내는 형태(repo 필드 채움). m1 키 == m3 읽기 키 고정용.
REPO_PAYLOAD = {
    "task_id": "t-200",
    "pr_id": "4",
    "pr_diff": "diff --git a/src/x.py b/src/x.py\n+code",  # 본문(비-URL)
    "clone_url": "https://github.com/owner/repo.git",
    "commit_sha": "27f5c96142260206ce714da1294aefbbddb0f4f6",
    "developer": {"id": "dev-9"},
}


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_verify_tests_contract(client):
    resp = await client.post("/verify/tests", json=VERIFY_PAYLOAD)
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_id"] == "t-002"
    assert data["agent"] == "test_verification"
    assert "issues" in data


@pytest.mark.asyncio
async def test_analyze_performance_contract(client):
    resp = await client.post("/analyze/performance", json=VERIFY_PAYLOAD)
    assert resp.status_code == 200
    assert resp.json()["agent"] == "performance"


# ---------------------------------------------------------------------------
# 계약 매핑 회귀 — m1 이 채워 보내는 repo 필드가 RepoInfo·Dev3Input 으로 흘러가는지
# (m1 키 변경 시 이 테스트가 깨져 즉시 알 수 있게 함)
# ---------------------------------------------------------------------------

def _fake_outputs():
    perf = SimpleNamespace(agent="performance", issues=[
        SimpleNamespace(
            severity="Major", file="src/x.py", line=8, message="N+1",
            rule_id="PERF-002", suggestion="배치 조회",
        ),
    ])
    tv = SimpleNamespace(agent="test_verification", issues=[])
    return [tv, perf]


@pytest.mark.asyncio
async def test_repo_fields_flow_into_repoinfo_and_dev3input(client, monkeypatch):
    """clone_url/commit_sha → RepoInfo, pr_diff/pr_id/developer → Dev3Input 으로 정확히 전달.

    실 clone·실행은 seam(_dev3_prepare_repo·_dev3_run) monkeypatch 로 고립하고 인자를 캡처한다.
    """
    captured: dict = {}

    def fake_prepare(repo):
        captured["repo"] = repo
        return "/tmp/dev3_fake_work_dir"

    def fake_run(dev3_input, work_dir):
        captured["inp"] = dev3_input
        captured["work_dir"] = work_dir
        return _fake_outputs()

    monkeypatch.setattr(appmain, "_dev3_prepare_repo", fake_prepare)
    monkeypatch.setattr(appmain, "_dev3_run", fake_run)
    # coverage seam(도커)은 단위테스트에서 no-op 으로 고립
    monkeypatch.setattr(appmain, "_dev3_measure_coverage", lambda work_dir: None)

    resp = await client.post("/analyze/performance", json=REPO_PAYLOAD)
    assert resp.status_code == 200

    repo = captured["repo"]
    inp = captured["inp"]
    # RepoInfo 매핑 (m1 키 고정)
    assert repo.clone_url == REPO_PAYLOAD["clone_url"]
    assert repo.commit_sha == REPO_PAYLOAD["commit_sha"]
    # Dev3Input 매핑
    assert inp.repo.clone_url == REPO_PAYLOAD["clone_url"]
    assert inp.repo.commit_sha == REPO_PAYLOAD["commit_sha"]
    assert inp.pr_diff == REPO_PAYLOAD["pr_diff"]   # 본문(비-URL)은 그대로 전달
    assert inp.pr_id == "4"
    assert inp.developer.id == "dev-9"
    assert captured["work_dir"] == "/tmp/dev3_fake_work_dir"

    # 가짜 AgentOutput → IssueItem 매핑까지 확인
    data = resp.json()
    assert data["agent"] == "performance"
    assert [i["rule_id"] for i in data["issues"]] == ["PERF-002"]
    assert data["summary"] == {"critical": 0, "major": 1, "minor": 0}


@pytest.mark.asyncio
async def test_minimal_payload_backward_compat_empty_issues(client):
    """repo 필드 없는 최소 payload(하위호환) → clone 불가 → 빈 issues + 200(가짜 없음)."""
    resp = await client.post("/analyze/performance", json=VERIFY_PAYLOAD)
    assert resp.status_code == 200
    data = resp.json()
    assert data["issues"] == []
    assert data["summary"] == {"critical": 0, "major": 0, "minor": 0}


# ---------------------------------------------------------------------------
# pr_diff 방어 — 값이 'http'로 시작하면 1회 fetch 해 본문으로 치환(실패 시 정직하게 빈 문자열)
# ---------------------------------------------------------------------------

def test_resolve_pr_diff_passthrough_when_body():
    body = "diff --git a/x b/x\n+1"
    assert appmain._resolve_pr_diff(body) == body


def test_resolve_pr_diff_fetches_when_url(monkeypatch):
    fetched = b"diff --git a/y.py b/y.py\n+2"

    class _FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return fetched

    monkeypatch.setattr(
        appmain.urllib.request, "urlopen", lambda req, timeout=None: _FakeResp()
    )
    out = appmain._resolve_pr_diff("https://github.com/o/r/pull/4.diff")
    assert out == fetched.decode("utf-8")


def test_resolve_pr_diff_empty_on_fetch_failure(monkeypatch):
    def _boom(req, timeout=None):
        raise OSError("network down")

    monkeypatch.setattr(appmain.urllib.request, "urlopen", _boom)
    # 실패 → 빈 문자열(가짜 diff 만들지 않음)
    assert appmain._resolve_pr_diff("http://example.com/x.diff") == ""
