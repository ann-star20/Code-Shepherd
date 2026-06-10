"""LangSmith 계측 인프라 — instrument 데코레이터 + LatencyCollector.

LANGCHAIN_API_KEY 환경변수:
  없으면 → LatencyCollector 로컬 타이밍 래퍼만 (LangSmith 없음)
  있으면 → LangSmith traceable + LatencyCollector 로컬 타이밍

LatencyCollector:
  with LatencyCollector() as col:
      ... @instrument 함수 호출 ...
  col.to_dict()  # {span_name: [ms, ...]}

lazy import: langsmith 미설치 환경에서도 import 시점에 절대 실패하지 않는다.
"""
from __future__ import annotations

import functools
import os
import threading
import time


# 스레드-로컬 컨텍스트 저장소
_local = threading.local()


class LatencyCollector:
    """@instrument 함수들의 소요 시간을 컨텍스트 기간 동안 수집하는 레코더.

    사용법:
        with LatencyCollector() as col:
            my_instrumented_fn()
        timings = col.to_dict()  # {"span_name": [ms, ...]}
    """

    def __init__(self) -> None:
        self._spans: list[tuple[str, float]] = []

    def __enter__(self) -> "LatencyCollector":
        _local.collector = self
        return self

    def __exit__(self, *args: object) -> None:
        _local.collector = None

    def record(self, name: str, ms: float) -> None:
        self._spans.append((name, ms))

    def to_dict(self) -> dict[str, list[float]]:
        """name → [ms, ...] 딕셔너리 반환. 한 번도 호출 안 된 단계는 포함 안 됨."""
        result: dict[str, list[float]] = {}
        for name, ms in self._spans:
            result.setdefault(name, []).append(ms)
        return result


def instrument(name: str, run_type: str = "tool"):
    """탐지기/LLM 호출을 계측한다.

    - 항상: 활성 LatencyCollector가 있으면 소요 ms 기록
    - LANGCHAIN_API_KEY 있으면: LangSmith traceable로 추가 감쌈
    - lazy import: langsmith 미설치여도 안전

    task_id·scan_id·pr_id는 main.run()의 parent run context에서 자동 상속됨.
    """
    def deco(fn):
        # LangSmith 래핑 여부 결정
        base_fn = fn
        if os.getenv("LANGCHAIN_API_KEY"):
            try:
                from langsmith import traceable  # lazy import
                base_fn = traceable(name=name, run_type=run_type)(fn)
            except ImportError:
                pass

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            collector = getattr(_local, "collector", None)
            if collector is not None:
                t0 = time.perf_counter()
                try:
                    return base_fn(*args, **kwargs)
                finally:
                    collector.record(name, (time.perf_counter() - t0) * 1000)
            return base_fn(*args, **kwargs)

        return wrapper
    return deco
