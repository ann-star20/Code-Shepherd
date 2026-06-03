"""
aggregate_graph.py — 파이프라인 2 LangGraph StateGraph 조립 (PRD 노드 I→M→N→O)

M0(Orchestrator)가 M2+M3의 AgentOutput을 묶어 POST /aggregate로 전달하면
이 그래프가 취합 → 코멘트 생성 → GitHub 등록 → (Critical 시) Slack 알림까지 처리한다.

파이프라인 흐름:
    START
     └─→ aggregate       (M2+M3 취합 + PostgreSQL 저장 + M4 push)
     └─→ comment_refine  (LLM 수준별 PR 코멘트 생성)
     └─→ github_comment  (GitHub PR 코멘트 등록 → github_comment_url 반환)
     └─→ [조건부 분기]
           ├─ Critical ≥ 1 → slack_notify (시니어 즉시 알림, 코멘트 URL 포함) → END
           └─ Critical = 0 → END

설계 노트:
    github_comment → slack_notify 순서는 의도적이다. slack_notify가
    github_comment_url을 알림에 포함할 수 있도록 GitHub 등록을 먼저 수행한다.
    (기존 slack_notify/github_comment 노드를 그대로 재사용 — Task 11 구현)

CLAUDE.md 준수:
    §3   LangSmith 콜백은 config로 주입 (함수 내부 하드코딩 금지)
    §6   자동 머지 없음 — 코멘트/알림만 수행
    §12  알림 실패는 파이프라인을 막지 않음 (각 노드에서 처리)
"""

import logging
import os

from langgraph.graph import END, StateGraph

from dev2.nodes.aggregate import aggregate_node
from dev2.nodes.comment_refine import comment_refine_node
from dev2.nodes.github_comment import github_comment_node
from dev2.nodes.slack_notify import slack_notify_node
from dev2.schema import AggregateState

logger = logging.getLogger(__name__)

# ── LangSmith 트레이서 (lazy 초기화 — graph.py와 동일 패턴) ────────────────────
_tracer = None


def _get_tracer():
    """LangSmith 트레이서 lazy 초기화 (langchain_core 미설치 환경 허용)."""
    global _tracer
    if _tracer is not None:
        return _tracer
    try:
        from langchain_core.callbacks import LangChainTracer  # noqa: PLC0415
        _tracer = LangChainTracer(project_name=os.getenv("LANGCHAIN_PROJECT", "dev2-local"))
    except ImportError:
        logger.debug("langchain_core 미설치 — LangSmith 트레이서 비활성화")
        _tracer = None
    return _tracer


# ── 조건부 엣지 라우터 ────────────────────────────────────────────────────────

def _route_after_github(state: AggregateState) -> str:
    """Critical ≥ 1 → slack_notify, 없으면 바로 END."""
    if state.get("total_summary", {}).get("critical", 0) >= 1:
        logger.info("_route_after_github: Critical 감지 → slack_notify 경로")
        return "slack_notify"
    return "end"


# ── 그래프 빌더 ───────────────────────────────────────────────────────────────

def build_aggregate_graph():
    """
    파이프라인 2 StateGraph를 조립하고 컴파일된 그래프를 반환한다.

    Returns:
        CompiledStateGraph — await graph.ainvoke(state) 로 실행
    """
    g = StateGraph(AggregateState)

    g.add_node("aggregate",      aggregate_node)
    g.add_node("comment_refine", comment_refine_node)
    g.add_node("github_comment", github_comment_node)
    g.add_node("slack_notify",   slack_notify_node)

    g.set_entry_point("aggregate")
    g.add_edge("aggregate",      "comment_refine")
    g.add_edge("comment_refine", "github_comment")

    # 조건부 엣지: Critical 유무에 따라 Slack 알림 후 종료 또는 즉시 종료
    g.add_conditional_edges(
        "github_comment",
        _route_after_github,
        {
            "slack_notify": "slack_notify",
            "end":          END,
        },
    )
    g.add_edge("slack_notify", END)

    compiled = g.compile()
    logger.debug("파이프라인 2 StateGraph 컴파일 완료 (aggregate → comment_refine → github → slack)")
    return compiled


# ── 진입점 ────────────────────────────────────────────────────────────────────

async def run_aggregate(payload_dict: dict) -> dict:
    """
    POST /aggregate BackgroundTasks 진입점.

    AggregatePayload.model_dump() 형식의 dict를 받아 AggregateState로 변환한 뒤
    파이프라인 2 그래프를 실행한다.

    Args:
        payload_dict: AggregatePayload dict (task_id, pr_id, developer, context, all_results)

    Returns:
        그래프 실행 결과 State dict
    """
    context = payload_dict.get("context", {}) or {}
    developer = payload_dict["developer"]

    initial: AggregateState = {
        "task_id":            payload_dict["task_id"],
        "pr_id":              payload_dict["pr_id"],
        "developer_id":       developer["id"],
        "skill_level":        developer["skill_level"],
        "tech_stack":         developer["tech_stack"],
        "architecture_docs":  context.get("architecture_docs", []),
        "coding_conventions": context.get("coding_conventions", ""),
        "previous_pr_issues": context.get("previous_pr_issues", []),
        "all_results":        payload_dict.get("all_results", []),
        "aggregated_issues":  [],
        "total_summary":      {},
        "comment_body":       "",
    }

    graph = build_aggregate_graph()
    tracer = _get_tracer()
    config = {"callbacks": [tracer]} if tracer else {}

    result = await graph.ainvoke(initial, config=config)
    logger.info(
        "run_aggregate 완료: task_id=%s, critical=%d",
        payload_dict["task_id"], result.get("total_summary", {}).get("critical", 0),
    )
    return result
