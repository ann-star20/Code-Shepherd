"""Task 17 — LatencyCollector TDD 테스트.

검증 핵심:
  1. @instrument 함수가 LatencyCollector 컨텍스트 안에서 호출되면 타이밍이 기록된다.
  2. 컨텍스트 밖에서는 타이밍이 기록되지 않는다(no side-effect).
  3. 여러 단계 → 여러 키, 같은 단계 반복 → 리스트로 누적.
  4. 기록 안 된 단계는 to_dict()에 아예 없다 (가짜 0 금지).
  5. 컨텍스트 종료 후에는 수집이 멈춘다.
  6. 키 없을 때 instrument()는 이제 원본 함수가 아닌 래퍼를 반환한다 (타이밍 지원).
"""
from __future__ import annotations

import importlib
import os
import sys
import time


# ════════════════════════════════════════════
# 헬퍼: harness 모듈 격리 재로드
# ════════════════════════════════════════════

def _fresh_harness(monkeypatch, has_key: bool = False):
    """harness를 fresh import하여 상태 격리."""
    if has_key:
        monkeypatch.setenv("LANGCHAIN_API_KEY", "fake-key")
    else:
        monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
    import harness
    importlib.reload(harness)
    return harness


# ════════════════════════════════════════════
# 1. LatencyCollector 기본 동작
# ════════════════════════════════════════════

def test_collector_records_span_for_instrumented_call(monkeypatch):
    """LatencyCollector 컨텍스트 안에서 @instrument 함수를 호출하면 타이밍이 기록된다."""
    harness = _fresh_harness(monkeypatch)

    @harness.instrument("stage_alpha")
    def alpha():
        return 42

    with harness.LatencyCollector() as col:
        alpha()

    d = col.to_dict()
    assert "stage_alpha" in d, "stage_alpha span이 기록돼야 한다"
    assert len(d["stage_alpha"]) == 1
    assert d["stage_alpha"][0] >= 0  # ms 값은 비음수


def test_collector_timing_is_positive_ms(monkeypatch):
    """실제 소요 시간(ms)이 기록된다 — sleep(0.05)이면 ≥ 30ms(여유 마진)."""
    harness = _fresh_harness(monkeypatch)

    @harness.instrument("slow_stage")
    def slow():
        time.sleep(0.05)
        return "done"

    with harness.LatencyCollector() as col:
        slow()

    ms = col.to_dict()["slow_stage"][0]
    assert ms >= 30, f"50ms sleep인데 {ms:.1f}ms로 기록됨 — 너무 짧다"


def test_collector_inactive_outside_context(monkeypatch):
    """컨텍스트 밖에서는 수집이 일어나지 않는다."""
    harness = _fresh_harness(monkeypatch)

    @harness.instrument("outside_stage")
    def fn():
        return 1

    # 컨텍스트 밖 호출 후, 이전에 만든 collector를 검사
    col = harness.LatencyCollector()
    fn()  # 컨텍스트 없이 호출
    assert col.to_dict() == {}, "컨텍스트 밖 호출은 기록되지 않아야 한다"


def test_collector_multiple_stages_separate_keys(monkeypatch):
    """서로 다른 @instrument 이름 → to_dict()에 각각 키로 기록된다."""
    harness = _fresh_harness(monkeypatch)

    @harness.instrument("stage_a")
    def fn_a():
        return "a"

    @harness.instrument("stage_b")
    def fn_b():
        return "b"

    @harness.instrument("stage_c")
    def fn_c():
        return "c"

    with harness.LatencyCollector() as col:
        fn_a()
        fn_b()
        fn_c()

    d = col.to_dict()
    assert set(d.keys()) == {"stage_a", "stage_b", "stage_c"}


def test_collector_same_stage_multiple_calls_accumulate(monkeypatch):
    """같은 @instrument 이름 → 여러 번 호출하면 ms 리스트에 누적된다."""
    harness = _fresh_harness(monkeypatch)

    @harness.instrument("repeated")
    def fn():
        return 0

    with harness.LatencyCollector() as col:
        fn()
        fn()
        fn()

    assert len(col.to_dict()["repeated"]) == 3


def test_collector_missing_stage_absent_from_dict(monkeypatch):
    """한 번도 호출 안 된 단계는 to_dict()에 아예 없다 (가짜 0 금지)."""
    harness = _fresh_harness(monkeypatch)

    @harness.instrument("present")
    def fn_present():
        return 1

    @harness.instrument("absent")
    def fn_absent():
        return 2

    with harness.LatencyCollector() as col:
        fn_present()
        # fn_absent()는 호출 안 함

    d = col.to_dict()
    assert "present" in d
    assert "absent" not in d, "호출 안 된 단계는 dict에 없어야 한다"


def test_collector_cleanup_after_context_exit(monkeypatch):
    """컨텍스트 종료 후 @instrument 함수 호출 → 기존 collector에 기록 안 됨."""
    harness = _fresh_harness(monkeypatch)

    @harness.instrument("after_exit")
    def fn():
        return 99

    with harness.LatencyCollector() as col:
        fn()  # 1회

    fn()  # 컨텍스트 종료 후 2회째

    # collector에는 1회만 기록돼야 한다
    assert len(col.to_dict()["after_exit"]) == 1


def test_collector_return_value_preserved(monkeypatch):
    """타이밍 래퍼가 원본 함수의 반환값을 보존한다."""
    harness = _fresh_harness(monkeypatch)

    @harness.instrument("returns_42")
    def fn():
        return 42

    with harness.LatencyCollector() as col:
        result = fn()

    assert result == 42


def test_collector_exception_propagated_but_timing_recorded(monkeypatch):
    """@instrument 함수가 예외를 던져도 타이밍은 기록되고, 예외는 전파된다."""
    harness = _fresh_harness(monkeypatch)

    @harness.instrument("failing_stage")
    def fn():
        raise ValueError("test error")

    with harness.LatencyCollector() as col:
        try:
            fn()
        except ValueError:
            pass

    d = col.to_dict()
    assert "failing_stage" in d, "예외 발생해도 타이밍은 기록돼야 한다"


# ════════════════════════════════════════════
# 2. instrument() 래퍼 행동 변경 확인
# ════════════════════════════════════════════

def test_instrument_no_key_wraps_fn_not_identity(monkeypatch):
    """키 없을 때 instrument()는 타이밍 지원 래퍼를 반환한다 (원본과 다름).

    (task16의 wrapped is my_fn 어설션은 LatencyCollector 지원 추가로 더 이상 성립 안 함)
    """
    harness = _fresh_harness(monkeypatch, has_key=False)

    def my_fn(x):
        return x * 2

    wrapped = harness.instrument("test_tool")(my_fn)
    # 래퍼이지만 원본 함수처럼 동작해야 한다
    assert wrapped(5) == 10, "래퍼가 원본 함수의 결과를 반환해야 한다"


def test_instrument_wrapper_works_without_collector(monkeypatch):
    """collector가 없어도 래퍼가 문제없이 동작한다."""
    harness = _fresh_harness(monkeypatch, has_key=False)

    @harness.instrument("no_collector")
    def fn(x, y):
        return x + y

    result = fn(3, 4)
    assert result == 7
