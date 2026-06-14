"""kms_client + orchestrator KMS context 채우기 테스트 — graceful 경로.

실제 네트워크/m0 없이 통과해야 한다(kms_client.search·analyze·m4 evaluate Mock).
"""

import pytest

from app import orchestrator
from app.contract import KmsSearchRequest, KmsSearchResponse, KmsSearchResult, M2OrchestrateRequest
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


def _req() -> M2OrchestrateRequest:
    return M2OrchestrateRequest(task_id="t-1", pr_id="42", pr_diff=PY_DIFF, trace_id="pr_abc")


# ── kms_client 단위 ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_kms_client_returns_none_when_url_unset(monkeypatch):
    monkeypatch.delenv("M0_URL", raising=False)
    monkeypatch.delenv("M0_BASE_URL", raising=False)
    resp = await orchestrator.kms_client.search(KmsSearchRequest(query="x"))
    assert resp is None


# ── 질의 빌더 ─────────────────────────────────────────────────────────────

def test_build_kms_query_extracts_changed_paths():
    q = orchestrator._build_kms_query(PY_DIFF)
    assert "src/db.py" in q


# ── orchestrator 연결 ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_context_filled_from_kms(monkeypatch):
    monkeypatch.setattr(orchestrator, "analyze", _fake_analyze)
    monkeypatch.setattr(orchestrator.m4_client, "evaluate", _no_m4)

    async def _fake_search(req):
        assert "src/db.py" in req.query
        return KmsSearchResponse(
            results=[KmsSearchResult(chunk_id="c-1", content="N+1 쿼리 방지 가이드", score=0.9)]
        )

    monkeypatch.setattr(orchestrator.kms_client, "search", _fake_search)
    req = _req()
    res = await orchestrator.run_m2_orchestration(req)
    assert res.kms_used is True
    assert req.context.architecture_docs == ["N+1 쿼리 방지 가이드"]


@pytest.mark.asyncio
async def test_graceful_when_kms_unavailable(monkeypatch):
    monkeypatch.setattr(orchestrator, "analyze", _fake_analyze)
    monkeypatch.setattr(orchestrator.m4_client, "evaluate", _no_m4)

    async def _no_kms(_req):
        return None

    monkeypatch.setattr(orchestrator.kms_client, "search", _no_kms)
    req = _req()
    res = await orchestrator.run_m2_orchestration(req)
    assert res.kms_used is False
    assert req.context.architecture_docs == []
    # KMS 없어도 분석은 그대로 진행
    assert res.static_analysis is not None
    assert res.security_scan is not None


@pytest.mark.asyncio
async def test_kms_skipped_when_context_already_filled(monkeypatch):
    monkeypatch.setattr(orchestrator, "analyze", _fake_analyze)
    monkeypatch.setattr(orchestrator.m4_client, "evaluate", _no_m4)

    called = {"n": 0}

    async def _spy_search(_req):
        called["n"] += 1
        return None

    monkeypatch.setattr(orchestrator.kms_client, "search", _spy_search)
    req = _req()
    req.context.coding_conventions = "사내 컨벤션 존재"
    res = await orchestrator.run_m2_orchestration(req)
    assert called["n"] == 0  # 이미 채워져 있으면 KMS 호출 안 함
    assert res.kms_used is False
