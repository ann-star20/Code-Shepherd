"""LangGraph StateGraph for M6 pipeline orchestration.

Celery tasks (run_pipeline_task, resume_pipeline_task) in tasks.py are thin wrappers
that invoke these compiled graphs. All step sequencing, conditional routing, and
per-node retry are controlled here. Redis Pub/Sub events (_emit/_log) are published
from within each node exactly as in the original Celery task implementations.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy
from typing_extensions import TypedDict

from app.worker.tasks import (
    _NO_CONCEPTS_FOUND_MESSAGE,
    _classify_error,
    _crawl_async,
    _emit,
    _extract_async,
    _prescan_async,
    _set_failed_async,
    _verify_async,
)


class PipelineState(TypedDict, total=False):
    session_id: str
    url: str
    doc_id: str
    skip: bool
    skip_reason: str
    awaiting_metadata: bool
    suggestions: list[str]
    source_prefix: str
    framework: str | None
    lang: str | None
    version: str | None
    chunks: list[str]
    staged: int
    no_concepts_found: bool
    extract_summary: dict[str, Any]
    is_valid: bool
    prescan_mismatch: bool
    discrepancies: list[str]
    prescan_llm: dict[str, Any]


async def prescan_node(state: PipelineState) -> PipelineState:
    session_id = state["session_id"]
    _emit(session_id, {"type": "step_update", "step": "Input", "status": "RUNNING"})
    try:
        ctx = await _prescan_async(session_id, state["url"])
        if ctx.get("skip"):
            _emit(session_id, {
                "type": "step_update", "step": "Input", "status": "SKIPPED",
                "reason": ctx.get("skip_reason", "중복 문서로 파이프라인을 건너뜁니다."),
            })
            _emit(session_id, {"type": "finished"})
        elif ctx.get("awaiting_metadata"):
            _emit(session_id, {
                "type": "metadata_required", "step": "Input",
                "doc_id": ctx["doc_id"], "url": ctx["url"],
                "suggestions": ctx.get("suggestions", []),
            })
        else:
            _emit(session_id, {"type": "step_update", "step": "Input", "status": "DONE"})
        return {**state, **ctx}
    except Exception:
        await _set_failed_async(session_id)
        raise


async def crawl_node(state: PipelineState) -> PipelineState:
    session_id = state["session_id"]
    _emit(session_id, {"type": "step_update", "step": "Crawler", "status": "RUNNING"})
    try:
        result = await _crawl_async(state)
        _emit(session_id, {"type": "step_update", "step": "Crawler", "status": "DONE"})
        return {**state, **result}
    except Exception:
        await _set_failed_async(session_id)
        raise


async def extract_node(state: PipelineState) -> PipelineState:
    session_id = state["session_id"]
    _emit(session_id, {"type": "step_update", "step": "Extractor", "status": "RUNNING"})
    try:
        result = await _extract_async(state)
        if result.get("no_concepts_found"):
            _emit(session_id, {
                "type": "step_update", "step": "Extractor", "status": "FAILED",
                "reason": _NO_CONCEPTS_FOUND_MESSAGE,
            })
        else:
            _emit(session_id, {"type": "step_update", "step": "Extractor", "status": "DONE"})
        return {**state, **result}
    except Exception as exc:
        reason = _classify_error(exc)
        _emit(session_id, {
            "type": "step_update", "step": "Extractor", "status": "FAILED", "reason": reason,
        })
        await _set_failed_async(session_id)
        raise


async def extract_verify_node(state: PipelineState) -> PipelineState:
    session_id = state["session_id"]
    if state.get("no_concepts_found"):
        _emit(session_id, {"type": "finished"})
        return state
    _emit(session_id, {"type": "step_update", "step": "ExtractVerifier", "status": "RUNNING"})
    try:
        result = await _verify_async(state)
        if not result.get("is_valid", True):
            reason = "; ".join(result.get("discrepancies") or ["검증 실패"])
            _emit(session_id, {
                "type": "step_update", "step": "ExtractVerifier",
                "status": "FAILED", "reason": reason,
            })
        elif result.get("prescan_mismatch"):
            _emit(session_id, {"type": "step_update", "step": "ExtractVerifier", "status": "WARN"})
        else:
            _emit(session_id, {"type": "step_update", "step": "ExtractVerifier", "status": "DONE"})
        _emit(session_id, {"type": "finished"})
        return {**state, **result}
    except Exception:
        _emit(session_id, {"type": "finished"})
        raise


def _route_after_prescan(state: PipelineState) -> str:
    if state.get("skip") or state.get("awaiting_metadata"):
        return END
    return "crawl"


_PRESCAN_RETRY = RetryPolicy(max_attempts=3, initial_interval=5)
_CRAWL_RETRY = RetryPolicy(max_attempts=3, initial_interval=10)
_EXTRACT_RETRY = RetryPolicy(max_attempts=3, initial_interval=60)
_VERIFY_RETRY = RetryPolicy(max_attempts=1, initial_interval=10)

full_pipeline_graph = (
    StateGraph(PipelineState)
    .add_node("prescan", prescan_node, retry_policy=_PRESCAN_RETRY)
    .add_node("crawl", crawl_node, retry_policy=_CRAWL_RETRY)
    .add_node("extract", extract_node, retry_policy=_EXTRACT_RETRY)
    .add_node("extract_verify", extract_verify_node, retry_policy=_VERIFY_RETRY)
    .add_edge(START, "prescan")
    .add_conditional_edges("prescan", _route_after_prescan, {"crawl": "crawl", END: END})
    .add_edge("crawl", "extract")
    .add_edge("extract", "extract_verify")
    .add_edge("extract_verify", END)
    .compile()
)

resume_pipeline_graph = (
    StateGraph(PipelineState)
    .add_node("crawl", crawl_node, retry_policy=_CRAWL_RETRY)
    .add_node("extract", extract_node, retry_policy=_EXTRACT_RETRY)
    .add_node("extract_verify", extract_verify_node, retry_policy=_VERIFY_RETRY)
    .add_edge(START, "crawl")
    .add_edge("crawl", "extract")
    .add_edge("extract", "extract_verify")
    .add_edge("extract_verify", END)
    .compile()
)
