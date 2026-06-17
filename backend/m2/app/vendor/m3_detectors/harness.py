"""LangSmith 계측 인프라 — instrument 데코레이터.

LANGCHAIN_API_KEY 환경변수:
  없으면 → no-op (원본 함수 그대로 반환, import 실패 없음)
  있으면 → langsmith.traceable 로 감쌈

lazy import: langsmith 미설치 환경에서도 import 시점에 절대 실패하지 않는다.
"""
from __future__ import annotations

import os


def instrument(name: str, run_type: str = "tool"):
    """탐지기/LLM 호출을 LangSmith run으로 감싼다. 키 없으면 원본 함수 그대로.

    task_id·scan_id·pr_id는 main.run()의 parent run context에서 자동 상속됨.
    (데코레이터는 definition time 적용 → runtime 값 직접 주입 불가)
    """
    def deco(fn):
        if not os.getenv("LANGCHAIN_API_KEY"):
            return fn
        try:
            from langsmith import traceable  # lazy import — 미설치여도 키 없으면 안 탐
        except ImportError:
            return fn
        return traceable(name=name, run_type=run_type)(fn)
    return deco
