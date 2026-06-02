"""Task 16 — harness.py TDD 테스트.

검증 핵심:
  1. 키 없을 때: no-op → 원본 함수 그대로 반환, 기존 테스트 전부 통과
  2. 키 있을 때 (MOCK): langsmith.traceable 정확히 1회 호출 확인
  3. langsmith 미설치 환경에서도 import 실패 없어야 함 (lazy import)
"""
import importlib
import os
import sys
from unittest.mock import MagicMock, patch


# ════════════════════════════════════════════
# 1. 키 없음 — no-op 검증 (★ 이 세션의 정상 상태)
# ════════════════════════════════════════════

def test_instrument_no_key_returns_original_fn(monkeypatch):
    """LANGCHAIN_API_KEY 없으면 데코레이터가 원본 함수 그대로 반환한다."""
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)

    # harness를 fresh import (다른 테스트 상태 격리)
    import harness
    importlib.reload(harness)

    def my_fn(x):
        return x * 2

    wrapped = harness.instrument("test_tool")(my_fn)
    assert wrapped is my_fn, "키 없을 때 instrument()는 원본 함수를 그대로 반환해야 한다"


def test_instrument_no_key_fn_executes_correctly(monkeypatch):
    """키 없을 때 데코레이팅된 함수가 정상 동작한다."""
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)

    import harness
    importlib.reload(harness)

    @harness.instrument("test_tool")
    def add(a, b):
        return a + b

    assert add(3, 4) == 7


def test_instrument_no_key_run_type_llm_noop(monkeypatch):
    """run_type='llm'이어도 키 없으면 no-op."""
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)

    import harness
    importlib.reload(harness)

    def llm_call(prompt):
        return f"answer:{prompt}"

    wrapped = harness.instrument("llm_call", "llm")(llm_call)
    assert wrapped is llm_call
    assert wrapped("hi") == "answer:hi"


def test_instrument_no_import_error_without_langsmith(monkeypatch):
    """langsmith 패키지가 없어도 harness import가 실패하지 않는다 (lazy import)."""
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)

    # langsmith를 sys.modules에서 제거해 미설치 시뮬레이션
    original = sys.modules.pop("langsmith", None)
    try:
        import harness
        importlib.reload(harness)
        # 데코레이터도 예외 없이 동작해야 함
        @harness.instrument("safe_tool")
        def fn():
            return 42
        assert fn() == 42
    finally:
        # 원복
        if original is not None:
            sys.modules["langsmith"] = original


# ════════════════════════════════════════════
# 2. 키 있음 — traceable 호출 확인 (MOCK)
# ════════════════════════════════════════════

def test_instrument_with_key_calls_traceable_once(monkeypatch):
    """LANGCHAIN_API_KEY 있으면 langsmith.traceable이 정확히 1회 호출된다."""
    monkeypatch.setenv("LANGCHAIN_API_KEY", "fake-key-for-test")

    mock_traceable = MagicMock(side_effect=lambda **kwargs: (lambda fn: fn))

    with patch.dict("sys.modules", {"langsmith": MagicMock(traceable=mock_traceable)}):
        import harness
        importlib.reload(harness)

        def detect():
            return []

        harness.instrument("nplus1")(detect)

    mock_traceable.assert_called_once_with(name="nplus1", run_type="tool")


def test_instrument_with_key_passes_run_type(monkeypatch):
    """run_type 인수가 traceable에 그대로 전달된다."""
    monkeypatch.setenv("LANGCHAIN_API_KEY", "fake-key-for-test")

    mock_traceable = MagicMock(side_effect=lambda **kwargs: (lambda fn: fn))

    with patch.dict("sys.modules", {"langsmith": MagicMock(traceable=mock_traceable)}):
        import harness
        importlib.reload(harness)

        @harness.instrument("memory_leak_llm", "llm")
        def _llm_call(prompt):
            return "ok"

    mock_traceable.assert_called_once_with(name="memory_leak_llm", run_type="llm")


def test_instrument_with_key_wraps_and_calls_original(monkeypatch):
    """키 있을 때도 원본 함수가 실행된다."""
    monkeypatch.setenv("LANGCHAIN_API_KEY", "fake-key-for-test")

    called = {"n": 0}

    def passthrough(**kwargs):
        """traceable처럼 fn을 받아 그대로 반환하는 identity wrapper."""
        def inner(fn):
            return fn
        return inner

    mock_traceable = MagicMock(side_effect=passthrough)

    with patch.dict("sys.modules", {"langsmith": MagicMock(traceable=mock_traceable)}):
        import harness
        importlib.reload(harness)

        @harness.instrument("my_tool")
        def my_fn(x):
            called["n"] += 1
            return x + 1

    assert my_fn(10) == 11
    assert called["n"] == 1


# ════════════════════════════════════════════
# 3. 탐지기에 @instrument 부착 확인
# ════════════════════════════════════════════

def test_decorated_detectors_importable(monkeypatch):
    """@instrument 부착된 탐지기들이 키 없이도 정상 import된다."""
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)

    import importlib
    for mod_name in [
        "performance.nplus1",
        "performance.complexity",
        "test_verification.coverage",
        "test_verification.missing_funcs",
        "test_verification.edge_cases",
        "performance.memory_leak",
        "main",
    ]:
        mod = importlib.import_module(mod_name)
        importlib.reload(mod)  # 환경변수 변경 반영
        assert mod is not None, f"{mod_name} import 실패"
