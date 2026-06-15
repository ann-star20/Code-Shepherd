"""m4 `/evaluate` 호출 client — graceful fallback.

`M4_URL`이 없거나 호출이 실패하면 None을 반환한다(분석 자체는 중단되지 않음).
공유 계약(M4EvaluateRequest/Response)만 사용하므로 m4 코드를 수정하지 않는다.
"""

from __future__ import annotations

import os

import httpx

from shared.contracts import M4EvaluateRequest, M4EvaluateResponse

_TIMEOUT = 30.0  # 초


def _base_url() -> str | None:
    url = os.getenv("M4_URL") or os.getenv("M4_BASE_URL")
    return url.rstrip("/") if url else None


async def evaluate(req: M4EvaluateRequest) -> M4EvaluateResponse | None:
    """m4 `/evaluate` 호출. 미설정·실패 시 None(graceful)."""
    base = _base_url()
    if not base:
        return None
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{base}/evaluate", json=req.model_dump(mode="json")
            )
            resp.raise_for_status()
            return M4EvaluateResponse(**resp.json())
    except (httpx.HTTPError, ValueError):
        return None
