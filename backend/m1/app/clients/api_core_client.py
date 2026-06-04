"""api-core 내부 API 클라이언트."""

from __future__ import annotations

import httpx
from fastapi import HTTPException, status

from shared.config import get_settings
from shared.logging import get_logger

logger = get_logger(__name__)


async def call_api_core_pr_ingest(payload: dict) -> dict:
    """POST /internal/pr-ingest — PR 메타를 api-core DB에 적재."""
    settings = get_settings()
    url = f"{settings.api_core_url.rstrip('/')}/internal/pr-ingest"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            json=payload,
            headers={"X-Internal-Token": settings.internal_service_token},
            timeout=15.0,
        )
    if resp.status_code == status.HTTP_404_NOT_FOUND:
        try:
            detail = resp.json().get("detail", "Not found")
        except Exception:
            detail = resp.text or "Not found"
        logger.warning(
            "pr_ingest_skipped",
            detail=detail,
            repository=payload.get("repository_full_name"),
        )
        raise HTTPException(status_code=404, detail=detail)
    if resp.status_code >= 400:
        logger.error(
            "pr_ingest_failed",
            status=resp.status_code,
            body=resp.text,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"api-core pr-ingest failed: {resp.status_code}",
        )
    return resp.json()
