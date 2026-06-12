"""GitHub diff fetch client — PR 웹훅이 준 diff_url에서 unified diff 본문을 가져온다.

GitHub PR 웹훅 payload에는 diff 본문이 없고 `diff_url`만 있다(기존 m1이 하던 fetch 역할).
`GITHUB_TOKEN`이 있으면 인증 헤더를 붙인다(프라이빗 repo·rate limit).
실패 시 None(graceful — 빈 diff면 decision이 skip 처리).
"""

from __future__ import annotations

import os

import httpx

_TIMEOUT = 30.0  # 초


async def fetch_diff(diff_url: str) -> str | None:
    """diff_url → unified diff 문자열. 실패 시 None."""
    if not diff_url:
        return None
    headers = {"Accept": "application/vnd.github.v3.diff"}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token.strip()}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(diff_url, headers=headers)
            resp.raise_for_status()
            return resp.text
    except httpx.HTTPError:
        return None
