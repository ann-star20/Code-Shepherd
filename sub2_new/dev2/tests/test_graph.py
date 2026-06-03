"""
test_graph.py — LangGraph StateGraph 조립 테스트

노드 순서: tool_router_agent → run_tools → vector_search → llm_judge
           → action_decider_agent → [조건부] → (escalate →) store

테스트 목표:
    1. 그래프가 final_output 리스트를 반환한다.
    2. Critical 이슈 발견 시 action_decider가 early_escalation → escalate 진입.
    3. Critical 없으면 escalate 건너뛰고 store로 간다.
    4. tool_router_agent → run_tools → ... 순서가 유지된다.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from dev2.schema import Dev2State
from dev2.graph import build_graph


# ── 공통 초기 State ────────────────────────────────────────────────────────────
INITIAL_STATE: Dev2State = {
    "task_id": "uuid-001",
    "pr_id": "1",
    "pr_diff": "+++ b/src/auth.py\n+query = sql + user",
    "developer_id": "dev-001",
    "skill_level": "junior",
    "tech_stack": ["python"],
    "architecture_docs": [],
    "coding_conventions": "",
    "previous_pr_issues": [],
    "static_raw": [],
    "security_raw": [],
    "enriched": [],
    "final_output": [],
    "tool_plan": None,
    "action_decision": None,
}

_CRITICAL_ISSUE = {
    "severity": "Critical",
    "line": 42,
    "file": "auth.py",
    "message": "SQL 인젝션",
    "rule_id": "B608",
    "suggestion": "파라미터 바인딩 사용",
    "similar_issues": [],
    "_source": "security",
    "confidence_score": 0.92,
}

_ACTION_EARLY_ESCALATION = {
    "recommended_action": "early_escalation",
    "reason": "Critical 1개",
    "confidence": 0.95,
    "signals": {"critical_count": 1, "major_count": 0, "minor_count": 0,
                "important_file_issue": False, "low_confidence_issue": False},
}

_ACTION_STORE_ONLY = {
    "recommended_action": "store_only",
    "reason": "이슈 없음",
    "confidence": 0.90,
    "signals": {"critical_count": 0, "major_count": 0, "minor_count": 0,
                "important_file_issue": False, "low_confidence_issue": False},
}


# ── 테스트 1: 그래프 기본 동작 — final_output 반환 ─────────────────────────────
@pytest.mark.asyncio
async def test_graph_returns_final_output():
    """빈 이슈 환경에서 그래프가 final_output 리스트를 반환하는지 확인."""
    with patch("dev2.nodes.run_tools._run_for_language", new_callable=AsyncMock,
               return_value={"static": [], "security": []}), \
         patch("dev2.nodes.store._persist", new_callable=AsyncMock), \
         patch("dev2.nodes.store._load_bigquery"):

        graph = build_graph()
        result = await graph.ainvoke(INITIAL_STATE)

        assert "final_output" in result
        assert isinstance(result["final_output"], list)


# ── 테스트 2: Critical → action_decider early_escalation → escalate 진입 ───────
@pytest.mark.asyncio
async def test_graph_escalates_on_critical():
    """
    Critical 이슈 → action_decider가 early_escalation 반환
    → escalate 노드의 notify_dev4 호출
    """
    critical_issue = _CRITICAL_ISSUE.copy()

    with patch("dev2.nodes.run_tools._run_for_language", new_callable=AsyncMock,
               return_value={"static": [], "security": [critical_issue]}), \
         patch("dev2.nodes.vector_search.vector_search_node", new_callable=AsyncMock,
               return_value={"enriched": [critical_issue]}), \
         patch("dev2.nodes.llm_judge.llm_judge_node", new_callable=AsyncMock,
               return_value={"enriched": [critical_issue]}), \
         patch("dev2.nodes.action_decider_agent.action_decider_agent_node",
               new_callable=AsyncMock,
               return_value={"action_decision": _ACTION_EARLY_ESCALATION}), \
         patch("dev2.nodes.escalate.notify_dev4", new_callable=AsyncMock) as mock_notify, \
         patch("dev2.nodes.store._persist", new_callable=AsyncMock), \
         patch("dev2.nodes.store._load_bigquery"):

        graph = build_graph()
        await graph.ainvoke(INITIAL_STATE)

        mock_notify.assert_called_once()


# ── 테스트 3: Critical 없음 → store_only → escalate 건너뜀 ────────────────────
@pytest.mark.asyncio
async def test_graph_skips_escalate_when_no_critical():
    """Minor만 있으면 action_decider가 store_only → escalate 미진입."""
    minor_issue = {
        "severity": "Minor", "line": 10, "file": "utils.py",
        "message": "lint", "rule_id": "E501", "suggestion": "fix",
        "similar_issues": [], "_source": "static", "confidence_score": 0.0,
    }

    with patch("dev2.nodes.run_tools._run_for_language", new_callable=AsyncMock,
               return_value={"static": [minor_issue], "security": []}), \
         patch("dev2.nodes.vector_search.vector_search_node", new_callable=AsyncMock,
               return_value={"enriched": [minor_issue]}), \
         patch("dev2.nodes.llm_judge.llm_judge_node", new_callable=AsyncMock,
               return_value={"enriched": [minor_issue]}), \
         patch("dev2.nodes.action_decider_agent.action_decider_agent_node",
               new_callable=AsyncMock,
               return_value={"action_decision": _ACTION_STORE_ONLY}), \
         patch("dev2.nodes.escalate.notify_dev4", new_callable=AsyncMock) as mock_notify, \
         patch("dev2.nodes.store._persist", new_callable=AsyncMock), \
         patch("dev2.nodes.store._load_bigquery"):

        graph = build_graph()
        await graph.ainvoke(INITIAL_STATE)

        mock_notify.assert_not_called()


# ── 테스트 4: tool_router_agent → run_tools 순서 확인 ─────────────────────────
@pytest.mark.asyncio
async def test_graph_tool_router_runs_before_run_tools():
    """tool_router_agent가 run_tools보다 먼저 실행되어 tool_plan을 채우는지 확인."""
    call_order = []

    async def fake_tool_router(state):
        call_order.append("tool_router_agent")
        return {"tool_plan": {"selected_tools": ["pylint"], "changed_files": [],
                              "detected_languages": [], "risk_keywords": [],
                              "dependency_changed": False, "llm_required": False, "reason": []}}

    async def fake_run_tools(state):
        call_order.append("run_tools")
        # tool_plan이 state에 있는지 확인
        assert state.get("tool_plan") is not None
        return {"static_raw": [], "security_raw": []}

    # graph.py가 노드 함수를 직접 import해서 바인딩하므로 graph 모듈에서 패치
    with patch("dev2.graph.tool_router_agent_node", new_callable=AsyncMock,
               side_effect=fake_tool_router), \
         patch("dev2.graph.run_tools_node", new_callable=AsyncMock,
               side_effect=fake_run_tools), \
         patch("dev2.nodes.store._persist", new_callable=AsyncMock), \
         patch("dev2.nodes.store._load_bigquery"):

        graph = build_graph()
        await graph.ainvoke(INITIAL_STATE)

    assert call_order.index("tool_router_agent") < call_order.index("run_tools")


# ── 테스트 5: action_decision이 final_output에 포함 ───────────────────────────
@pytest.mark.asyncio
async def test_graph_action_decision_in_output():
    """final_output의 summary에 recommended_action이 포함되는지 확인."""
    minor_issue = {
        "severity": "Minor", "line": 1, "file": "a.py", "message": "lint",
        "rule_id": "E501", "suggestion": "fix", "similar_issues": [],
        "_source": "static", "confidence_score": 0.0,
    }

    with patch("dev2.nodes.run_tools._run_for_language", new_callable=AsyncMock,
               return_value={"static": [minor_issue], "security": []}), \
         patch("dev2.nodes.vector_search.vector_search_node", new_callable=AsyncMock,
               return_value={"enriched": [minor_issue]}), \
         patch("dev2.nodes.llm_judge.llm_judge_node", new_callable=AsyncMock,
               return_value={"enriched": [minor_issue]}), \
         patch("dev2.nodes.action_decider_agent.action_decider_agent_node",
               new_callable=AsyncMock,
               return_value={"action_decision": _ACTION_STORE_ONLY}), \
         patch("dev2.nodes.store._persist", new_callable=AsyncMock), \
         patch("dev2.nodes.store._load_bigquery"):

        graph = build_graph()
        result = await graph.ainvoke(INITIAL_STATE)

        final = result.get("final_output", [])
        if final:
            summary = final[0].get("summary", {})
            assert "recommended_action" in summary
