"""노드 실행 trace 단위테스트 — _traced 래퍼 + run_review_traced (LLM 미호출)."""
from __future__ import annotations

from typing import Literal

import pytest
from langgraph.types import Command

from contracts import Finding
from src import graph as graph_mod
from src.graph import _trace_var, _traced


@pytest.fixture
def trace_list():
    """래퍼가 기록할 trace 리스트를 contextvar에 설정."""
    trace: list[dict] = []
    token = _trace_var.set(trace)
    yield trace
    _trace_var.reset(token)


def _make_finding(verdict: str = "violation") -> Finding:
    return Finding(
        rule_id="CONV-API-001", verdict=verdict, severity="Major",
        rule_quote="q", file="", evidence_lines=[], reasoning="r", fp_note=None,
    )


# ── dict 반환 노드 ────────────────────────────────────────────────────────────

def test_traced_records_dict_node(trace_list):
    def fake_judge(state):
        return {"findings": [_make_finding(), _make_finding("no_violation")]}

    wrapped = _traced("judge", fake_judge)
    result = wrapped({})

    assert result["findings"][0].rule_id == "CONV-API-001"
    assert len(trace_list) == 1
    rec = trace_list[0]
    assert rec["node"] == "judge"
    assert rec["ok"] is True
    assert "2" in rec["summary"]          # findings 2건
    assert "violation 1" in rec["summary"]
    assert isinstance(rec["ms"], int)


# ── Command 반환 노드 (③) ─────────────────────────────────────────────────────

def test_traced_records_command_node(trace_list):
    def fake_check(state) -> Command[Literal["judge"]]:
        return Command(update={"route": "proceed"}, goto="judge")

    wrapped = _traced("check_sufficiency", fake_check)
    result = wrapped({})

    assert isinstance(result, Command)    # Command 그대로 반환 (라우팅 보존)
    assert result.goto == "judge"
    assert trace_list[0]["summary"] == "route=proceed"


def test_traced_preserves_return_annotation():
    """functools.wraps 가 Command[Literal[...]] 반환 타입을 보존해야
    LangGraph 그래프 컴파일(타깃 검증)이 깨지지 않는다."""
    def fake_check(state) -> Command[Literal["retrieve", "judge"]]:
        return Command(update={}, goto="judge")

    wrapped = _traced("check_sufficiency", fake_check)
    assert wrapped.__annotations__ == fake_check.__annotations__


# ── 예외 노드 ─────────────────────────────────────────────────────────────────

def test_traced_records_failure_and_reraises(trace_list):
    def broken(state):
        raise ValueError("boom")

    wrapped = _traced("retrieve", broken)
    with pytest.raises(ValueError):
        wrapped({})

    rec = trace_list[0]
    assert rec["ok"] is False
    assert "ValueError" in rec["summary"]


# ── contextvar 미설정 시 no-op ────────────────────────────────────────────────

def test_traced_noop_without_context():
    """run_review_traced 밖에서 호출되면 기록 없이 동작만 한다."""
    wrapped = _traced("judge", lambda state: {"findings": []})
    assert wrapped({}) == {"findings": []}


# ── 그래프 컴파일 (trace 래퍼 적용 후에도 Command 라우팅 유효) ────────────────

def test_build_graph_compiles_with_traced_nodes():
    app = graph_mod.build_graph()
    node_names = set(app.get_graph().nodes)
    assert {"assemble_input", "extract_concepts", "retrieve",
            "check_sufficiency", "judge", "compose_comment"} <= node_names
