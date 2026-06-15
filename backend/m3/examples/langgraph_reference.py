"""LangGraph 1.2.4 공식 문법 레퍼런스 — 이 파일의 문법만 사용한다 (버전 함정 방지).

실행 검증: `.venv\\Scripts\\python examples\\langgraph_reference.py` → 3개 예제 전부 OK 출력.
다른 버전(0.x 블로그/기억 속 API) 문법 금지. 여기 없는 패턴이 필요하면 먼저 이 파일에
실행 가능한 예제를 추가·검증한 뒤 사용한다.

예제 구성:
  A) 직선 그래프 — D2 파이프라인 골조 (StateGraph / add_node / add_edge / START / END)
  B) Command 라우팅 — ③ check_sufficiency 의 proceed/requery(1회)/gap 분기 패턴 그대로
  C) interrupt()/Command(resume=...) — human-in-the-loop (체크포인터 필요)
"""
from __future__ import annotations

from typing import Literal, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


# ── A) 직선 그래프 (D2 ⓪→⑤ 골조) ────────────────────────────────────────

class LinearState(TypedDict, total=False):
    text: str
    steps: list[str]


def step_a(state: LinearState) -> dict:
    # 노드는 "변경분 dict"만 반환한다 (state 전체를 반환하지 않는다)
    return {"steps": state.get("steps", []) + ["a"]}


def step_b(state: LinearState) -> dict:
    return {"steps": state["steps"] + ["b"]}


def build_linear():
    builder = StateGraph(LinearState)
    builder.add_node("a", step_a)
    builder.add_node("b", step_b)
    builder.add_edge(START, "a")
    builder.add_edge("a", "b")
    builder.add_edge("b", END)
    return builder.compile()


# ── B) Command 라우팅 — ③ check_sufficiency 분기 패턴 ───────────────────

class RouteState(TypedDict, total=False):
    chunks: list[str]
    requery_count: int        # 전 파이프라인 합산 상한 1 (contracts.ReviewState 와 동일)
    route_log: list[str]


def retrieve(state: RouteState) -> dict:
    # 재질의면 두 번째엔 결과가 생기는 시나리오 흉내
    found = ["chunk-1"] if state.get("requery_count", 0) > 0 else []
    return {"chunks": found, "route_log": state.get("route_log", []) + ["retrieve"]}


def check_sufficiency(state: RouteState) -> Command[Literal["retrieve", "judge", "gap"]]:
    """Command(update=..., goto=...) 로 상태 갱신과 라우팅을 한 번에.

    add_conditional_edges 대신 이 패턴을 표준으로 쓴다 (카운터 갱신과 분기가 원자적).
    """
    log = state.get("route_log", []) + ["check"]
    if state.get("chunks"):
        return Command(update={"route_log": log}, goto="judge")
    if state.get("requery_count", 0) < 1:                      # 재질의 1회 상한
        return Command(
            update={"requery_count": state.get("requery_count", 0) + 1, "route_log": log},
            goto="retrieve",
        )
    return Command(update={"route_log": log}, goto="gap")


def judge(state: RouteState) -> dict:
    return {"route_log": state["route_log"] + ["judge"]}


def gap(state: RouteState) -> dict:
    return {"route_log": state["route_log"] + ["gap"]}


def build_router():
    builder = StateGraph(RouteState)
    builder.add_node("retrieve", retrieve)
    builder.add_node("check", check_sufficiency)   # Command 반환 노드 — 나가는 edge 등록 불필요
    builder.add_node("judge", judge)
    builder.add_node("gap", gap)
    builder.add_edge(START, "retrieve")
    builder.add_edge("retrieve", "check")
    builder.add_edge("judge", END)
    builder.add_edge("gap", END)
    return builder.compile()


# ── C) interrupt() + Command(resume=...) — human-in-the-loop ────────────

class HilState(TypedDict, total=False):
    draft: str
    approved: str


def ask_human(state: HilState) -> dict:
    # interrupt()는 그래프를 멈추고 페이로드를 밖으로 던진다.
    # 재개 시 Command(resume=값) 의 값이 interrupt() 의 반환값이 된다.
    answer = interrupt({"question": "이 코멘트 승인?", "draft": state["draft"]})
    return {"approved": answer}


def build_hil():
    builder = StateGraph(HilState)
    builder.add_node("ask_human", ask_human)
    builder.add_edge(START, "ask_human")
    builder.add_edge("ask_human", END)
    # interrupt 사용 시 체크포인터 필수 + invoke 에 thread_id config 필수
    return builder.compile(checkpointer=InMemorySaver())


# ── 실행 검증 ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # A
    out = build_linear().invoke({"text": "hi"})
    assert out["steps"] == ["a", "b"], out
    print("A) linear OK:", out["steps"])

    # B — 첫 검색 빈 결과 → requery 1회 → 성공 → judge (gap 아님)
    out = build_router().invoke({})
    assert out["requery_count"] == 1, out
    assert out["route_log"] == ["retrieve", "check", "retrieve", "check", "judge"], out
    print("B) command routing OK:", out["route_log"])

    # C — interrupt 발생 → __interrupt__ 확인 → resume
    graph = build_hil()
    config = {"configurable": {"thread_id": "demo-1"}}
    out = graph.invoke({"draft": "LGTM"}, config)
    assert "__interrupt__" in out, out
    print("C) interrupted with payload:", out["__interrupt__"][0].value["question"])
    out = graph.invoke(Command(resume="approve"), config)
    assert out["approved"] == "approve", out
    print("C) resume OK:", out["approved"])

    print("\n전부 OK: 이 문법이 이 repo의 LangGraph 기준이다 (langgraph==1.2.4)")
