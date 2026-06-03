"""
graph.py — Dev2 LangGraph StateGraph 조립

이 모듈은 Dev2 분석 파이프라인의 5개 노드를 StateGraph로 조립하고
조건부 엣지(Critical 에스컬레이션)를 정의한다.

파이프라인 흐름:
    START
     └─→ run_tools      (ESLint/Pylint/Bandit/pip-audit 병렬 실행)
     └─→ vector_search  (pgVector RAG Retrieve — 유사 이슈 검색)
     └─→ llm_judge      (RAG Generate — claude-sonnet-4-6 severity 판단)
     └─→ [조건부 분기]
           ├─ Critical ≥ 1 → escalate (Dev4 즉시 알림)  → store
           └─ Critical = 0 → store (escalate 건너뜀)
     └─→ store          (PostgreSQL + BigQuery 이중 적재)
     └─→ END

Agentic Workflow 설계:
    _route_after_judge() — Critical 유무에 따른 동적 경로 결정.
    이것이 "단순 파이프라인"과 "AI Native Agentic Workflow"를 구분하는 핵심.
    LLM 판단 결과를 기반으로 실행 경로가 바뀐다.

CLAUDE.md 준수:
    §3     LangSmith 콜백은 config로 주입 (run_dev2의 graph.ainvoke config 참고)
    §4     Critical ≥ 1 → escalate, Major ≥ 3 → rework (Dev4 3-Way 판정)
    §5-A   final_output = [AgentOutput dict, ...] (Output Contract)
    §6     타임아웃: common/harness.py run_parallel_agents() — 직접 gather 금지
    §9     LLM: claude-sonnet-4-6
    §10-2  에이전트 출력은 Pydantic으로 검증 (store 노드에서 처리)

run_dev2() 호출 방식 (Dev1 Orchestrator):
    # common/harness.py의 run_parallel_agents 사용 (CLAUDE.md §6)
    results = await run_parallel_agents(
        agents=[
            ("static_analysis", run_dev2, (initial_state,), {}),
        ],
        db_pool=pool,
        pr_trace_id=pr_trace,
        task_id=initial_state["task_id"],
    )
"""

import logging
import os

from langgraph.graph import END, StateGraph

from dev2.nodes.action_decider_agent import action_decider_agent_node
from dev2.nodes.escalate import escalate_node
from dev2.nodes.llm_judge import llm_judge_node
from dev2.nodes.run_tools import run_tools_node
from dev2.nodes.store import store_node
from dev2.nodes.tool_router_agent import tool_router_agent_node
from dev2.nodes.vector_search import vector_search_node
from dev2.schema import Dev2State

logger = logging.getLogger(__name__)

# ── LangSmith 트레이서 ────────────────────────────────────────────────────────
# [CLAUDE.md §3] LangSmith 트레이서 (LANGCHAIN_PROJECT=dev2-{github_id})
# lazy import: langsmith/langchain_core가 미설치된 환경에서 graph.py import 허용
_tracer = None

def _get_tracer():
    """LangSmith 트레이서 lazy 초기화 (환경변수 LANGCHAIN_TRACING_V2=true 시 활성화)"""
    global _tracer
    if _tracer is not None:
        return _tracer
    try:
        from langchain_core.callbacks import LangChainTracer  # noqa: PLC0415
        project = os.getenv("LANGCHAIN_PROJECT", "dev2-local")
        _tracer = LangChainTracer(project_name=project)
        logger.debug("LangSmith 트레이서 초기화 완료 (project=%s)", project)
    except ImportError:
        logger.debug("langchain_core 미설치 — LangSmith 트레이서 비활성화")
        _tracer = None
    return _tracer


# ── 조건부 엣지 라우터 ────────────────────────────────────────────────────────

def route_after_action_decider(state: Dev2State) -> str:
    """
    Agentic Workflow 조건부 분기:
        action_decision.recommended_action == "early_escalation" → "escalate"
        그 외 (request_rework / needs_human_review / store_only)    → "store"

    request_rework / needs_human_review는 M2가 직접 처리하지 않고
    recommended_action 값만 store에 기록해 M0/Dev4가 참고하도록 한다.

    Args:
        state: action_decider_agent가 채운 action_decision 포함 Dev2State

    Returns:
        "escalate" 또는 "store"
    """
    action_decision: dict = state.get("action_decision") or {}
    recommended = action_decision.get("recommended_action", "store_only")

    if recommended == "early_escalation":
        logger.info("route_after_action_decider: early_escalation → escalate 경로")
        return "escalate"

    logger.debug("route_after_action_decider: %s → store 경로", recommended)
    return "store"


# backward compatibility — 기존 테스트/코드가 _route_after_judge를 참조하는 경우 대비
_route_after_judge = route_after_action_decider


# ── 그래프 빌더 ───────────────────────────────────────────────────────────────

def build_graph():
    """
    Dev2 LangGraph StateGraph를 조립하고 컴파일된 그래프를 반환한다.

    노드 순서:
        run_tools → vector_search → llm_judge → [조건부] → (escalate →) store

    에지 구조:
        run_tools ──→ vector_search (항상)
        vector_search ──→ llm_judge (항상)
        llm_judge ──→ escalate | store (조건부: Critical 유무)
        escalate ──→ store (항상)
        store ──→ END (항상)

    Returns:
        CompiledStateGraph — await graph.ainvoke(state) 로 실행
    """
    g = StateGraph(Dev2State)

    # ── 노드 등록 (7개) ────────────────────────────────────────────────────────
    g.add_node("tool_router_agent",    tool_router_agent_node)    # PR 맥락 기반 도구 선택
    g.add_node("run_tools",            run_tools_node)            # 선택된 도구 병렬 실행
    g.add_node("vector_search",        vector_search_node)        # RAG Retrieve (pgVector)
    g.add_node("llm_judge",            llm_judge_node)            # RAG Generate + concept 매핑
    g.add_node("action_decider_agent", action_decider_agent_node) # 후속 액션 추천
    g.add_node("escalate",             escalate_node)             # Critical 에스컬레이션
    g.add_node("store",                store_node)                # OLTP+OLAP 이중 저장

    # ── 엣지 정의 ──────────────────────────────────────────────────────────────
    g.set_entry_point("tool_router_agent")
    g.add_edge("tool_router_agent",    "run_tools")
    g.add_edge("run_tools",            "vector_search")
    g.add_edge("vector_search",        "llm_judge")
    g.add_edge("llm_judge",            "action_decider_agent")

    # 조건부 엣지: action_decider_agent 추천값 기반 분기
    g.add_conditional_edges(
        "action_decider_agent",
        route_after_action_decider,
        {
            "escalate": "escalate",  # early_escalation → 에스컬레이션 후 store
            "store":    "store",     # 그 외 → 바로 store
        },
    )
    g.add_edge("escalate", "store")
    g.add_edge("store",    END)

    compiled = g.compile()
    logger.debug("Dev2 StateGraph 컴파일 완료 (7 nodes: tool_router → ... → action_decider → store)")
    return compiled


# ── Dev2 에이전트 진입점 ──────────────────────────────────────────────────────

async def run_dev2(initial_state: Dev2State) -> list[dict]:
    """
    Dev2 에이전트 진입점 — StateGraph를 실행하고 final_output을 반환한다.

    [CLAUDE.md §3] LangSmith 콜백은 config로 주입 (함수 내부 하드코딩 금지).
    [CLAUDE.md §3] agent_traces 기록은 common/harness.py AgentHarness가 담당.
       → run_parallel_agents()에서 자동 처리되므로 여기서 직접 INSERT 금지.

    Dev1 Orchestrator 호출 방식:
        # common/harness.py의 run_parallel_agents 사용 (CLAUDE.md §6)
        results = await run_parallel_agents(
            agents=[
                ("static_analysis", run_dev2, (initial_state,), {}),
            ],
            db_pool=pool,
            pr_trace_id=pr_trace,
            task_id=initial_state["task_id"],
        )

    Args:
        initial_state: Dev2State — Dev1 Orchestrator가 채운 PRReviewState 기반

    Returns:
        list[dict] — AgentOutput dict 리스트 (CLAUDE.md §5-A Output Contract)
    """
    graph = build_graph()

    # [CLAUDE.md §3] LangSmith 콜백 config로 주입
    tracer = _get_tracer()
    config = {"callbacks": [tracer]} if tracer else {}

    result = await graph.ainvoke(initial_state, config=config)

    final_output = result.get("final_output", [])
    logger.info(
        "run_dev2 완료: final_output %d개 (task_id=%s)",
        len(final_output), initial_state.get("task_id", "?"),
    )
    return final_output
