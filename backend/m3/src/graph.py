"""LangGraph 조립 — 노드 6개 + ③ 조건 분기 + 실행 trace

문법 기준: examples/langgraph_reference.py 패턴 A(직선) + B(Command 라우팅).
D3: ③ check_sufficiency가 Command(goto=...) 로 3갈래 분기.
  proceed    → judge → compose_comment → END
  requery    → retrieve (루프, 1회 상한)
  gap_report → compose_comment → END
Command 반환 노드에는 나가는 edge를 등록하지 않는다 (reference.py §B 규칙).

D5: _traced 래퍼가 노드별 실행 기록(단계·요약·ms·성공여부)을 contextvar 에 누적.
State(contracts — 동결)는 건드리지 않는다. run_review_traced() 로만 노출되는
부가 정보이며, requery 루프 시 retrieve·③ 가 두 번 기록된다 (실제 흐름 그대로).
"""
from __future__ import annotations

import functools
import logging
import time
from collections.abc import Callable
from contextvars import ContextVar

logger = logging.getLogger("m3.graph")

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from contracts import ReviewInput, ReviewOutput, ReviewState
from src.nodes.assemble_input import assemble_input
from src.nodes.check_sufficiency import check_sufficiency
from src.nodes.compose_comment import compose_comment
from src.nodes.extract_concepts import extract_concepts
from src.nodes.judge import judge
from src.nodes.retrieve import retrieve

# run_review_traced 가 설정 — 미설정(None)이면 trace 기록 없이 동작 (오버헤드 0)
_trace_var: ContextVar[list | None] = ContextVar("dev3_trace", default=None)
# SSE 스트리밍용 — 노드마다 호출되는 emit 콜백 (asyncio.to_thread 컨텍스트 복사로 전달)
_emit_var: ContextVar[Callable | None] = ContextVar("dev3_emit", default=None)

_NODE_LABELS: dict[str, str] = {
    "assemble_input": "⓪ 입력 수집",
    "extract_concepts": "① 개념 추출",
    "retrieve": "② KMS 검색",
    "check_sufficiency": "③ 충분성 판단",
    "judge": "④ 규칙 판정",
    "compose_comment": "⑤ 코멘트 생성",
}


def _summarize(node: str, update: dict) -> str:
    """노드 산출(State 갱신분)에서 핵심 1줄 — 기존 데이터만 사용, 추가 LLM 호출 없음."""
    if node == "assemble_input":
        return f"pr_context {len(update.get('pr_context', ''))}자"
    if node == "extract_concepts":
        return (f"개념 {len(update.get('concepts', []))}개 · "
                f"질의 {len(update.get('queries', []))}개")
    if node == "retrieve":
        chunks = update.get("chunks", [])
        rule_ids = sorted({c.rule_id for c in chunks})
        return f"청크 {len(chunks)}개 ({', '.join(rule_ids) if rule_ids else '없음'})"
    if node == "check_sufficiency":
        return f"route={update.get('route', '?')}"
    if node == "judge":
        findings = update.get("findings", [])
        violations = sum(1 for f in findings if f.verdict == "violation")
        return f"findings {len(findings)}건 (violation {violations})"
    if node == "compose_comment":
        if update.get("gap_report"):
            return "지침공백 리포트 + 신규 지침 제안"
        return f"코멘트 {len(update.get('comment_md', ''))}자"
    return ""


def _traced(name: str, fn):
    """노드 실행 기록 래퍼. functools.wraps 가 반환 타입 어노테이션
    (③의 Command[Literal[...]])을 보존해 LangGraph 라우팅 검증이 유지된다."""
    @functools.wraps(fn)
    def wrapper(state):
        trace = _trace_var.get()
        emit = _emit_var.get()
        t0 = time.perf_counter()
        if emit is not None:
            emit({"type": "node_start", "node": name, "label": _NODE_LABELS.get(name, name)})
        try:
            result = fn(state)
        except Exception as exc:
            ms = int((time.perf_counter() - t0) * 1000)
            entry = {
                "type": "node_done",
                "node": name, "label": _NODE_LABELS.get(name, name),
                "ms": ms,
                "summary": f"{type(exc).__name__}: {exc}", "ok": False,
            }
            logger.error("[node=%-20s] FAIL %dms | %s: %s",
                         name, ms, type(exc).__name__, exc)
            if trace is not None:
                trace.append({k: v for k, v in entry.items() if k != "type"})
            if emit is not None:
                emit(entry)
            raise
        update = result.update if isinstance(result, Command) else (result or {})
        ms = int((time.perf_counter() - t0) * 1000)
        summary = _summarize(name, update or {})
        entry = {
            "type": "node_done",
            "node": name, "label": _NODE_LABELS.get(name, name),
            "ms": ms,
            "summary": summary, "ok": True,
        }
        logger.info("[node=%-20s] OK   %dms | %s", name, ms, summary)
        if trace is not None:
            trace.append({k: v for k, v in entry.items() if k != "type"})
        if emit is not None:
            emit(entry)
        return result
    return wrapper


def build_graph():
    builder = StateGraph(ReviewState)

    builder.add_node("assemble_input", _traced("assemble_input", assemble_input))
    builder.add_node("extract_concepts", _traced("extract_concepts", extract_concepts))
    builder.add_node("retrieve", _traced("retrieve", retrieve))
    builder.add_node("check_sufficiency", _traced("check_sufficiency", check_sufficiency))  # Command 반환 — 나가는 edge 없음
    builder.add_node("judge", _traced("judge", judge))
    builder.add_node("compose_comment", _traced("compose_comment", compose_comment))

    builder.add_edge(START, "assemble_input")
    builder.add_edge("assemble_input", "extract_concepts")
    builder.add_edge("extract_concepts", "retrieve")
    builder.add_edge("retrieve", "check_sufficiency")
    # check_sufficiency → judge / retrieve / compose_comment (Command가 동적 결정)
    builder.add_edge("judge", "compose_comment")
    builder.add_edge("compose_comment", END)

    return builder.compile()


_app = None


def run_review_traced(
    inp: ReviewInput, emit_fn: Callable | None = None
) -> tuple[ReviewOutput, list[dict], dict]:
    """run_review + 노드 실행 trace + RAGAS 품질 점수. http_adapter·Streamlit 타임라인용.

    emit_fn: 노드 이벤트마다 호출되는 콜백(dict) — SSE 스트리밍용.
             asyncio.to_thread 에서 실행되므로 thread-safe 하게 구현해야 한다.
    """
    from src.ragas_eval import evaluate_ragas

    global _app
    if _app is None:
        _app = build_graph()

    trace: list[dict] = []
    trace_token = _trace_var.set(trace)
    emit_token = _emit_var.set(emit_fn)
    try:
        state = _app.invoke({
            "diff": inp.diff,
            "file_paths": inp.file_paths,
            "repo_meta": inp.repo_meta,
        })
    finally:
        _trace_var.reset(trace_token)
        _emit_var.reset(emit_token)

    output = ReviewOutput(
        findings=state.get("findings", []),
        comment_md=state.get("comment_md", ""),
        gap_report=state.get("gap_report"),
    )

    findings = state.get("findings") or []
    violations = [f for f in findings if f.verdict == "violation"]
    if violations:
        question = " ".join(
            f"{f.rule_id}: {f.rule_quote}" for f in violations[:3]
        )
    else:
        question = " ".join(state.get("queries", [])[:2]) or inp.diff[:300]

    answer = state.get("comment_md", "")
    all_chunks = [c for c in (state.get("chunks") or []) if hasattr(c, "text")]
    violated_ids = {f.rule_id for f in violations}
    relevant = [c for c in all_chunks if c.rule_id in violated_ids]
    contexts = [c.text for c in (relevant or all_chunks)]
    ragas_scores = evaluate_ragas(question, answer, contexts)

    return output, trace, ragas_scores


def run_review(inp: ReviewInput) -> ReviewOutput:
    """어댑터(웹훅/Streamlit/하네스)가 부르는 단일 진입점 — 계약 불변."""
    return run_review_traced(inp)[0]
