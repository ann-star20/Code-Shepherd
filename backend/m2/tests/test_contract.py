"""계약 테스트 — m2 엔드포인트."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

ANALYZE_PAYLOAD = {
    "task_id": "t-001",
    "pr_id": "42",
    "pr_diff": "diff --git ...",
    "trace_id": "pr_0123456789ab",
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
async def test_analyze_static_contract(client):
    resp = await client.post("/analyze/static", json=ANALYZE_PAYLOAD)
    assert resp.status_code == 200
    data = resp.json()
    # M2AnalyzeResponse 호환 필드 (하위호환)
    assert data["task_id"] == "t-001"
    assert data["agent"] == "static_analysis"
    assert "issues" in data
    assert "summary" in data
    # MODULE_CONTRACT AgentResult 필드
    assert data["module_id"] == "module_2"
    assert data["agent_name"] == "StaticAnalysisAgent"
    assert data["status"] in ("success", "fail", "hitl_pending")
    assert data["validation_result"] in ("pass", "fail", "skip")
    assert data["sub_trace_id"].startswith("pr_0123456789ab_static_analysis_")
    assert data["next_agent"] is None


@pytest.mark.asyncio
async def test_analyze_security_contract(client):
    resp = await client.post("/analyze/security", json=ANALYZE_PAYLOAD)
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent"] == "security_scan"
    assert data["agent_name"] == "SecurityScanAgent"
    assert data["module_id"] == "module_2"
    assert data["sub_trace_id"].startswith("pr_0123456789ab_security_scan_")
