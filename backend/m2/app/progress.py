"""m2 실시간 파이프라인 진행상태 — 인메모리 저장.

프론트(SecurityPage)가 폴링으로 단계별 진행을 읽어 파이프라인을 실시간으로
시각화한다. 진행상태는 휘발성이라 DB가 아닌 모듈 전역 dict에 둔다(데모용 최소 구현).

단계 키(STAGE_KEYS)는 프론트 M2PipelineFlow의 STAGES와 동일한 순서/이름이다.
"""

from __future__ import annotations

import threading
from typing import Any, Literal, TypedDict

StageStatus = Literal["pending", "running", "success", "fail"]

STAGE_KEYS: list[str] = ["run_tools", "vector_search", "llm_judge", "store"]


class StageState(TypedDict):
    key: str
    status: StageStatus
    ms: int | None


class ProgressState(TypedDict):
    status: Literal["running", "done", "error"]
    stages: list[StageState]
    result: dict[str, Any] | None
    error: str | None


# 누적 방지를 위한 상한 (초과 시 가장 오래된 항목 제거)
_MAX_ENTRIES = 200

_lock = threading.Lock()
_store: dict[str, ProgressState] = {}


def start(task_id: str) -> None:
    """task_id 진행상태를 초기화(running, 전 단계 pending)한다."""
    with _lock:
        if len(_store) >= _MAX_ENTRIES:
            oldest = next(iter(_store))
            _store.pop(oldest, None)
        _store[task_id] = {
            "status": "running",
            "stages": [{"key": k, "status": "pending", "ms": None} for k in STAGE_KEYS],
            "result": None,
            "error": None,
        }


def set_stage(task_id: str, key: str, status: StageStatus, ms: int | None = None) -> None:
    """단계 상태를 갱신한다. ms가 주어지면 소요시간(밀리초)도 기록한다."""
    with _lock:
        st = _store.get(task_id)
        if not st:
            return
        for s in st["stages"]:
            if s["key"] == key:
                s["status"] = status
                if ms is not None:
                    s["ms"] = ms
                break


def finish(task_id: str, result: dict[str, Any]) -> None:
    """분석 완료 — status=done, 결과 요약을 저장한다."""
    with _lock:
        st = _store.get(task_id)
        if not st:
            return
        st["status"] = "done"
        st["result"] = result


def fail(task_id: str, msg: str) -> None:
    """분석 실패 — status=error, 메시지를 저장한다."""
    with _lock:
        st = _store.get(task_id)
        if not st:
            return
        st["status"] = "error"
        st["error"] = msg


def get(task_id: str) -> ProgressState | None:
    """진행상태를 반환한다. 없으면 None."""
    with _lock:
        return _store.get(task_id)
