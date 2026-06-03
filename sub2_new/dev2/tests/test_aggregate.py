"""
test_aggregate.py — 파이프라인 2 (aggregate → comment_refine → github → slack) 테스트

Task 9~13:
    1. aggregate_node: M2+M3 취합 + severity 정렬 + total_summary 집계
    2. aggregate_node: 빈 결과 처리
    3. comment_refine_node: Mock 코멘트 생성 + LLM 실패 폴백
    4. POST /aggregate → 202 Accepted
    5. aggregate_graph: Critical → slack_notify 경로 / no-Critical → slack 스킵

Mock 전략 (CLAUDE.md §13 — 실제 DB/LLM/외부 API 없이 통과):
    - insert_aggregated_result: PostgreSQL 저장 스킵
    - _post_github_comment: GitHub API 호출 스킵
    - _send_slack_alert: Slack Webhook 호출 스킵 (호출 여부로 라우팅 검증)
    - run_aggregate: 엔드포인트 접수 검증 시 파이프라인 스킵
"""

import os

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, patch

from dev2.main import app
from dev2.schema import AggregateState

# M2 결과 (static_analysis + security_scan) — Critical 1건 포함
ALL_RESULTS_CRITICAL = [
    {"agent": "static_analysis", "task_id": "u1",
     "issues": [{"severity": "Major", "line": 30, "file": "app.py",
                 "message": "복잡도 높음", "rule_id": "SA-COMPLEXITY",
                 "suggestion": "함수 분리", "similar_issues": []}],
     "summary": {"critical": 0, "major": 1, "minor": 0}, "execution_ms": 500},
    {"agent": "security_scan", "task_id": "u1",
     "issues": [{"severity": "Critical", "line": 12, "file": "auth.py",
                 "message": "SQL 인젝션", "rule_id": "B608",
                 "suggestion": "파라미터 쿼리", "similar_issues": []}],
     "summary": {"critical": 1, "major": 0, "minor": 0}, "execution_ms": 300},
]


def _base_state(**overrides) -> AggregateState:
    state: AggregateState = {
        "task_id": "u1", "pr_id": "42", "developer_id": "dev-001",
        "skill_level": "junior", "tech_stack": ["python"],
        "architecture_docs": [], "coding_conventions": "", "previous_pr_issues": [],
        "all_results": [], "aggregated_issues": [], "total_summary": {},
        "comment_body": "",
    }
    state.update(overrides)
    return state


# ── aggregate_node ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_aggregate_node_combines_and_sorts():
    from dev2.nodes.aggregate import aggregate_node

    state = _base_state(all_results=ALL_RESULTS_CRITICAL)
    with patch("dev2.nodes.aggregate.insert_aggregated_result", new_callable=AsyncMock):
        result = await aggregate_node(state)

    assert result["total_summary"]["critical"] == 1
    assert result["total_summary"]["major"] == 1
    # Critical이 먼저 정렬돼야 함
    assert result["aggregated_issues"][0]["severity"] == "Critical"
    # agent 태그가 각 이슈에 부착됐는지
    assert result["aggregated_issues"][0]["agent"] == "security_scan"


@pytest.mark.asyncio
async def test_aggregate_node_empty_results():
    from dev2.nodes.aggregate import aggregate_node

    state = _base_state(task_id="u2", pr_id="2", all_results=[])
    with patch("dev2.nodes.aggregate.insert_aggregated_result", new_callable=AsyncMock):
        result = await aggregate_node(state)

    assert result["aggregated_issues"] == []
    assert result["total_summary"] == {"critical": 0, "major": 0, "minor": 0}


# ── comment_refine_node ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_comment_refine_mock_includes_summary():
    from dev2.nodes.comment_refine import comment_refine_node

    state = _base_state(
        aggregated_issues=[
            {"severity": "Critical", "file": "auth.py", "line": 12,
             "message": "SQL 인젝션", "rule_id": "B608",
             "suggestion": "파라미터화된 쿼리 사용", "agent": "security_scan",
             "similar_issues": []}
        ],
        total_summary={"critical": 1, "major": 0, "minor": 0},
    )
    with patch.dict("os.environ", {"USE_MOCK_LLM": "true"}):
        result = await comment_refine_node(state)

    assert "comment_body" in result
    assert len(result["comment_body"]) > 0
    assert "Critical" in result["comment_body"]


@pytest.mark.asyncio
async def test_comment_refine_fallback_on_llm_failure():
    from dev2.nodes.comment_refine import comment_refine_node

    state = _base_state(
        task_id="u2", pr_id="2", skill_level="senior",
        total_summary={"critical": 0, "major": 0, "minor": 0},
    )
    with patch.dict("os.environ", {"USE_MOCK_LLM": "false"}), \
         patch("dev2.nodes.comment_refine.ChatAnthropic") as mock_llm:
        mock_llm.return_value.ainvoke = AsyncMock(side_effect=Exception("LLM 오류"))
        result = await comment_refine_node(state)

    # 폴백: 빈 결과여도 코멘트 본문은 생성됨
    assert "comment_body" in result
    assert len(result["comment_body"]) > 0


# ── POST /aggregate 엔드포인트 ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_aggregate_endpoint_accepted():
    with patch("dev2.api.aggregate.run_aggregate", new_callable=AsyncMock):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.post("/aggregate", json={
                "task_id": "u1", "pr_id": "42",
                "developer": {"id": "dev-001", "skill_level": "junior", "tech_stack": ["python"]},
                "all_results": ALL_RESULTS_CRITICAL,
            })
    assert r.status_code == 202
    assert r.json()["task_id"] == "u1"


# ── aggregate_graph 전체 경로 ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_aggregate_graph_critical_triggers_slack():
    """Critical 이슈 → github_comment → slack_notify 경로 확인"""
    from dev2.aggregate_graph import build_aggregate_graph

    initial = _base_state(all_results=ALL_RESULTS_CRITICAL)

    with patch.dict("os.environ", {"USE_MOCK_LLM": "true"}), \
         patch("dev2.nodes.aggregate.insert_aggregated_result", new_callable=AsyncMock), \
         patch("dev2.nodes.github_comment._post_github_comment",
               new_callable=AsyncMock, return_value="https://github.com/org/repo/pull/42#1"), \
         patch("dev2.nodes.slack_notify._send_slack_alert", new_callable=AsyncMock) as mock_slack:
        graph = build_aggregate_graph()
        result = await graph.ainvoke(initial)

    # Critical 있으므로 Slack 알림 노드가 실행됐어야 함
    mock_slack.assert_called_once()
    assert result["total_summary"]["critical"] == 1
    assert result["aggregated_issues"][0]["severity"] == "Critical"


@pytest.mark.asyncio
async def test_aggregate_graph_no_critical_skips_slack():
    """Critical 없음 → slack_notify 건너뜀 → 바로 END"""
    from dev2.aggregate_graph import build_aggregate_graph

    no_critical = [
        {"agent": "static_analysis", "task_id": "u2",
         "issues": [{"severity": "Minor", "line": 5, "file": "app.py",
                     "message": "lint", "rule_id": "E501",
                     "suggestion": "fix", "similar_issues": []}],
         "summary": {"critical": 0, "major": 0, "minor": 1}, "execution_ms": 100},
    ]
    initial = _base_state(task_id="u2", pr_id="99", skill_level="senior",
                          all_results=no_critical)

    with patch.dict("os.environ", {"USE_MOCK_LLM": "true"}), \
         patch("dev2.nodes.aggregate.insert_aggregated_result", new_callable=AsyncMock), \
         patch("dev2.nodes.github_comment._post_github_comment",
               new_callable=AsyncMock, return_value=None), \
         patch("dev2.nodes.slack_notify._send_slack_alert", new_callable=AsyncMock) as mock_slack:
        graph = build_aggregate_graph()
        result = await graph.ainvoke(initial)

    # Critical 없으므로 Slack 알림 노드는 호출되지 않아야 함
    mock_slack.assert_not_called()
    assert result["total_summary"]["critical"] == 0
