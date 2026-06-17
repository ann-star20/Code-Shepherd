"""내부 API — m1 웹훅 → PR 적재."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db import get_session
from shared.logging import get_logger

from ..dependencies_internal import verify_internal_token
from ..services.pr_service import ingest_pr_from_webhook

router = APIRouter()
logger = get_logger(__name__)


class PRIngestBody(BaseModel):
    repository_full_name: str
    sender_github_login: str
    pr_number: int = Field(..., ge=1)
    pr_url: str | None = None
    action: str = "opened"
    pull_request: dict | None = None


@router.post("/pr-ingest", dependencies=[Depends(verify_internal_token)])
async def pr_ingest(
    body: PRIngestBody,
    db: AsyncSession = Depends(get_session),
):
    result = await ingest_pr_from_webhook(
        db,
        repository_full_name=body.repository_full_name,
        sender_github_login=body.sender_github_login,
        pr_number=body.pr_number,
        pr_url=body.pr_url,
        action=body.action,
        pull_request=body.pull_request,
    )
    logger.info(
        "pr_ingested",
        pr_id=str(result.pr_id),
        team_id=str(result.team_id),
        created=result.created,
        repo=body.repository_full_name,
        pr_number=body.pr_number,
    )
    return {
        "pr_id": str(result.pr_id),
        "team_id": str(result.team_id),
        "created": result.created,
        "status": "ingested",
    }
