"""HITL 수정 피드백 → LangSmith Feedback 기록. PRD §22."""

from __future__ import annotations

import json
import os
from typing import Optional


def record_hitl_feedback(
    run_id: str,
    before_json: dict,
    after_json: dict,
    app_mode: str | None = None,
) -> Optional[str]:
    """관리자 HITL 수정 diff를 LangSmith Feedback으로 기록한다.

    PROD: Client().create_feedback(key='hitl_correction', score=0) 호출.
    DEV: no-op — None 반환.

    Returns: feedback ID str (PROD) or None (DEV/오류).
    """
    mode = app_mode or os.getenv("APP_MODE", "development")
    if mode != "production":
        return None

    try:
        from langsmith import Client

        diff_keys = [k for k in after_json if before_json.get(k) != after_json.get(k)]
        comment = json.dumps(
            {"before": before_json, "after": after_json, "diff_keys": diff_keys},
            ensure_ascii=False,
        )
        client = Client()
        feedback = client.create_feedback(
            run_id=run_id,
            key="hitl_correction",
            score=0,
            comment=comment,
        )
        return str(feedback.id)
    except Exception:
        return None
