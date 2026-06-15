"""progress.py + run-case 실시간 파이프라인 테스트.

실제 분석 도구/네트워크 없이 통과해야 한다(analyze·m4 evaluate를 Mock).
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app import main, orchestrator, progress
from app.contract import M2OrchestrateRequest
from app.main import app
from shared.contracts import IssueItem, IssueSummary

PY_DIFF = """diff --git a/src/db.py b/src/db.py
--- a/src/db.py
+++ b/src/db.py
@@ -0,0 +1,2 @@
+def add(a, b):
+    return a + b
"""


def _fake_analyze(_diff, agent):
    issue = IssueItem(severity="Major", message=f"{agent} finding", rule_id="SA-X")
    return [issue], IssueSummary(major=1), 5


async def _no_m4(_req):
    return None


# ── progress 모듈 단위 ────────────────────────────────────────────────────

def test_start_initializes_pending_stages():
    progress.start("t-prog-1")
    st = progress.get("t-prog-1")
    assert st is not None
    assert st["status"] == "running"
    assert [s["key"] for s in st["stages"]] == progress.STAGE_KEYS
    assert all(s["status"] == "pending" for s in st["stages"])


def test_set_stage_updates_status_and_ms():
    progress.start("t-prog-2")
    progress.set_stage("t-prog-2", "run_tools", "running")
    progress.set_stage("t-prog-2", "run_tools", "success", ms=42)
    st = progress.get("t-prog-2")
    run_tools = next(s for s in st["stages"] if s["key"] == "run_tools")
    assert run_tools["status"] == "success"
    assert run_tools["ms"] == 42


def test_finish_and_fail():
    progress.start("t-prog-3")
    progress.finish("t-prog-3", {"found": True})
    assert progress.get("t-prog-3")["status"] == "done"
    progress.start("t-prog-4")
    progress.fail("t-prog-4", "boom")
    assert progress.get("t-prog-4")["status"] == "error"
    assert progress.get("t-prog-4")["error"] == "boom"


def test_get_unknown_returns_none():
    assert progress.get("does-not-exist") is None


# ── 단계 보고 통합 ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_orchestration_reports_all_stages(monkeypatch):
    monkeypatch.setattr(orchestrator, "analyze", _fake_analyze)
    monkeypatch.setattr(orchestrator.m4_client, "evaluate", _no_m4)

    progress.start("t-stage")
    req = M2OrchestrateRequest(task_id="t-stage", pr_id="101", pr_diff=PY_DIFF)
    await orchestrator.run_m2_orchestration(req, task_id="t-stage")

    st = progress.get("t-stage")
    assert st["status"] == "done"
    assert all(s["status"] == "success" for s in st["stages"])
    assert st["result"]["staticIssues"] == 1
    assert st["result"]["securityIssues"] == 1
    assert st["result"]["found"] is True


@pytest.mark.asyncio
async def test_run_case_invalid_name_rejected():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/orchestrate/run-case/..%2Fetc")
    assert resp.status_code in (400, 404)


@pytest.mark.asyncio
async def test_run_case_unknown_case_404():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/orchestrate/run-case/no_such_case_zzz")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_status_unknown_task_404():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/orchestrate/status/unknown-task-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_run_case_triggers_and_returns_task_id(monkeypatch, tmp_path):
    monkeypatch.setattr(orchestrator, "analyze", _fake_analyze)
    monkeypatch.setattr(orchestrator.m4_client, "evaluate", _no_m4)

    # 임시 케이스 디렉터리 구성 → M2_CASE_ROOT 치환
    case_dir = tmp_path / "mixed_case_01"
    case_dir.mkdir()
    (case_dir / "vulnerable.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    monkeypatch.setattr(main, "M2_CASE_ROOT", str(tmp_path))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/orchestrate/run-case/mixed_case_01")
    assert resp.status_code == 200
    data = resp.json()
    assert "task_id" in data
    assert data["pr_id"] == "101"
    # 진행상태가 생성돼 있어야 한다 (백그라운드 분석 시작)
    assert progress.get(data["task_id"]) is not None
