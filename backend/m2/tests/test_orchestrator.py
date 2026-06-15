"""orchestrator.py 테스트 — 분석 라우팅·m4 호출·graceful fallback.

실제 분석 도구/네트워크 없이 통과해야 한다(analyze·m4 evaluate를 Mock).
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app import orchestrator
from app.contract import M2OrchestrateRequest
from app.main import app
from shared.contracts import IssueItem, IssueSummary, M4EvaluateResponse

PY_DIFF = """diff --git a/src/db.py b/src/db.py
--- a/src/db.py
+++ b/src/db.py
@@ -0,0 +1,2 @@
+def add(a, b):
+    return a + b
"""

MD_ONLY_DIFF = """diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -0,0 +1,1 @@
+# Hello
"""


def _fake_analyze(_diff, agent):
    issue = IssueItem(severity="Major", message=f"{agent} finding", rule_id="SA-X")
    return [issue], IssueSummary(major=1), 5


async def _fake_evaluate(_req):
    return M4EvaluateResponse(
        task_id="t-1", pr_id="42", verdict="rework", comment_body="needs work"
    )


def _req(diff: str) -> M2OrchestrateRequest:
    return M2OrchestrateRequest(task_id="t-1", pr_id="42", pr_diff=diff, trace_id="pr_abc")


@pytest.mark.asyncio
async def test_skip_when_docs_only(monkeypatch):
    monkeypatch.setattr(orchestrator, "analyze", _fake_analyze)
    res = await orchestrator.run_m2_orchestration(_req(MD_ONLY_DIFF))
    assert res.status == "skip"
    assert res.ran_agents == []
    assert res.static_analysis is None


@pytest.mark.asyncio
async def test_runs_both_agents_and_calls_m4(monkeypatch):
    monkeypatch.setattr(orchestrator, "analyze", _fake_analyze)
    monkeypatch.setattr(orchestrator.m4_client, "evaluate", _fake_evaluate)
    res = await orchestrator.run_m2_orchestration(_req(PY_DIFF))
    assert res.status == "success"
    assert res.ran_agents == ["static_analysis", "security_scan"]
    assert res.static_analysis is not None
    assert res.security_scan is not None
    assert res.m4_called is True
    assert res.verdict == "rework"
    assert res.comment_body == "needs work"


@pytest.mark.asyncio
async def test_graceful_when_m4_unavailable(monkeypatch):
    monkeypatch.setattr(orchestrator, "analyze", _fake_analyze)

    async def _no_m4(_req):
        return None

    monkeypatch.setattr(orchestrator.m4_client, "evaluate", _no_m4)
    res = await orchestrator.run_m2_orchestration(_req(PY_DIFF))
    assert res.m4_called is False
    assert res.verdict is None
    # 분석 결과는 그대로 살아 있어야 한다
    assert res.static_analysis is not None
    assert res.security_scan is not None


@pytest.mark.asyncio
async def test_orchestrate_endpoint(monkeypatch):
    monkeypatch.setattr(orchestrator, "analyze", _fake_analyze)

    async def _no_m4(_req):
        return None

    monkeypatch.setattr(orchestrator.m4_client, "evaluate", _no_m4)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/orchestrate/review",
            json={"task_id": "t-1", "pr_id": "42", "pr_diff": PY_DIFF},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["ran_agents"] == ["static_analysis", "security_scan"]
    assert data["static_analysis"]["agent_name"] == "StaticAnalysisAgent"
