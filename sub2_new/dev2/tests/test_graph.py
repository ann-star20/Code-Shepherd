"""
test_graph.py — LangGraph StateGraph 조립 테스트

Task 5: build_graph() + run_dev2() 종단 테스트

테스트 목표:
    1. 그래프가 final_output 리스트를 반환한다.
    2. Critical 이슈 발견 시 escalate 노드(notify_dev4)가 호출된다.
    3. Critical 없는 경우 escalate를 건너뛰고 바로 store로 간다.

Mock 전략:
    - _run_for_language: 실제 CLI 도구 실행 대신 dict 반환
    - _search: pgVector 검색 스킵
    - llm_judge_node: LLM API 호출 스킵 (enriched 직접 반환)
    - notify_dev4: httpx 외부 요청 스킵
    - _persist: PostgreSQL INSERT 스킵
    - _load_bigquery: BigQuery 스킵

CLAUDE.md §5-A: final_output = [AgentOutput dict, ...]
CLAUDE.md §11:  PRReviewState 기반 초기 State 구조
"""

import pytest
from unittest.mock import patch, AsyncMock

from dev2.schema import Dev2State
from dev2.graph import build_graph


# ── 공통 초기 State ────────────────────────────────────────────────────────────
# [CLAUDE.md §11] PRReviewState 기반 초기 State — Dev1 Orchestrator가 채워주는 필드
INITIAL_STATE: Dev2State = {
    # PRReviewState 필드 (Dev1이 채움)
    "task_id": "uuid-001",
    "pr_id": "1",
    "pr_diff": "+++ b/src/auth.py\n+query = sql + user",
    "developer_id": "dev-001",
    "skill_level": "junior",
    "tech_stack": ["python"],
    "architecture_docs": [],
    "coding_conventions": "",
    "previous_pr_issues": [],
    # Dev2 전용 필드 (초기값)
    "static_raw": [],
    "security_raw": [],
    "enriched": [],
    "final_output": [],
}

# Critical 이슈 픽스처 (escalate 분기 테스트용)
_CRITICAL_ISSUE = {
    "severity": "Critical",
    "line": 42,
    "file": "auth.py",
    "message": "SQL 인젝션",
    "rule_id": "SEC-001",
    "suggestion": "파라미터 바인딩 사용",
    "similar_issues": [],
    "_source": "security",
}


# ── 테스트 1: 그래프 기본 동작 — final_output 반환 ─────────────────────────────
@pytest.mark.asyncio
async def test_graph_returns_final_output():
    """
    빈 이슈 환경에서 그래프가 final_output 리스트를 반환하는지 확인.

    모든 외부 의존성(CLI 도구, pgVector, LLM, DB)을 Mock으로 대체한다.
    """
    with patch("dev2.nodes.run_tools._run_for_language", new_callable=AsyncMock,
               return_value={"static": [], "security": []}), \
         patch("dev2.nodes.store._persist", new_callable=AsyncMock), \
         patch("dev2.nodes.store._load_bigquery"):

        graph = build_graph()
        result = await graph.ainvoke(INITIAL_STATE)

        assert "final_output" in result
        assert isinstance(result["final_output"], list)


# ── 테스트 2: Critical 이슈 → escalate 노드 실행 ──────────────────────────────
@pytest.mark.asyncio
async def test_graph_escalates_on_critical():
    """
    Critical 이슈 발견 시 escalate 노드의 notify_dev4가 호출되는지 확인.

    흐름: run_tools → vector_search → llm_judge → [Critical 감지] → escalate → store
    조건부 엣지(_route_after_judge)가 Critical 이슈를 올바르게 분기해야 한다.
    """
    critical_issue = _CRITICAL_ISSUE.copy()

    with patch("dev2.nodes.run_tools._run_for_language", new_callable=AsyncMock,
               return_value={"static": [], "security": [critical_issue]}), \
         patch("dev2.nodes.vector_search.vector_search_node", new_callable=AsyncMock,
               return_value={"enriched": [critical_issue]}), \
         patch("dev2.nodes.llm_judge.llm_judge_node", new_callable=AsyncMock,
               return_value={"enriched": [critical_issue]}), \
         patch("dev2.nodes.escalate.notify_dev4", new_callable=AsyncMock) as mock_notify, \
         patch("dev2.nodes.store._persist", new_callable=AsyncMock), \
         patch("dev2.nodes.store._load_bigquery"):

        graph = build_graph()
        await graph.ainvoke(INITIAL_STATE)

        # Critical 이슈 → escalate 노드 진입 → notify_dev4 호출 검증
        mock_notify.assert_called_once()


# ── 테스트 3: Critical 없음 → escalate 건너뜀 ─────────────────────────────────
@pytest.mark.asyncio
async def test_graph_skips_escalate_when_no_critical():
    """
    Critical 이슈가 없으면 escalate 노드를 건너뛰고 바로 store로 가는지 확인.

    Minor 이슈만 있을 때 notify_dev4가 호출되지 않아야 한다.
    """
    minor_issue = {
        "severity": "Minor",
        "line": 10,
        "file": "utils.py",
        "message": "변수명 snake_case 위반",
        "rule_id": "STYLE-001",
        "suggestion": "user_id 사용",
        "similar_issues": [],
        "_source": "static",
    }

    with patch("dev2.nodes.run_tools._run_for_language", new_callable=AsyncMock,
               return_value={"static": [minor_issue], "security": []}), \
         patch("dev2.nodes.vector_search.vector_search_node", new_callable=AsyncMock,
               return_value={"enriched": [minor_issue]}), \
         patch("dev2.nodes.llm_judge.llm_judge_node", new_callable=AsyncMock,
               return_value={"enriched": [minor_issue]}), \
         patch("dev2.nodes.escalate.notify_dev4", new_callable=AsyncMock) as mock_notify, \
         patch("dev2.nodes.store._persist", new_callable=AsyncMock), \
         patch("dev2.nodes.store._load_bigquery"):

        graph = build_graph()
        await graph.ainvoke(INITIAL_STATE)

        # Minor만 있으면 escalate 노드 진입 안 함 → notify_dev4 미호출
        mock_notify.assert_not_called()
