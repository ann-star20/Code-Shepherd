"""PR ingest 및 팀별 조회 — pull_requests + teams."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.pull_request import PullRequest
from ..models.team import Team, TeamMember
from ..models.user import User
from .team_service import _get_team_or_404, get_membership


@dataclass
class PRIngestResult:
    pr_id: uuid.UUID
    created: bool
    team_id: uuid.UUID


@dataclass
class PRListItem:
    id: uuid.UUID
    user_id: uuid.UUID
    author_login: str
    github_pr_number: int
    github_pr_url: str | None
    status: str
    submitted_at: datetime
    is_lgtm: bool


def map_github_pr_status(action: str, pull_request: dict) -> str:
    if pull_request.get("merged"):
        return "merged"
    if action == "closed":
        return "closed"
    return "open"


async def ingest_pr_from_webhook(
    db: AsyncSession,
    *,
    repository_full_name: str,
    sender_github_login: str,
    pr_number: int,
    pr_url: str | None,
    action: str,
    pull_request: dict | None = None,
) -> PRIngestResult:
    repo = repository_full_name.strip()
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="repository_full_name is required",
        )

    team_result = await db.execute(
        select(Team).where(Team.github_repo_full_name == repo)
    )
    team = team_result.scalar_one_or_none()
    if team is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No team registered for this repository",
        )

    user_result = await db.execute(
        select(User).where(User.github_id == sender_github_login)
    )
    user = user_result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="GitHub user not registered in the platform",
        )

    membership = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team.team_id,
            TeamMember.user_id == user.user_id,
        )
    )
    if membership.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PR author is not a member of the team for this repository",
        )

    pr_status = map_github_pr_status(action, pull_request or {})

    existing = await db.execute(
        select(PullRequest).where(
            PullRequest.repository_full_name == repo,
            PullRequest.github_pr_number == pr_number,
        )
    )
    row = existing.scalar_one_or_none()
    created = row is None
    if row is None:
        row = PullRequest(
            user_id=user.user_id,
            repository_full_name=repo,
            github_pr_number=pr_number,
            github_pr_url=pr_url,
            status=pr_status,
        )
        db.add(row)
    else:
        row.user_id = user.user_id
        row.github_pr_url = pr_url or row.github_pr_url
        row.status = pr_status
        row.submitted_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(row)
    return PRIngestResult(pr_id=row.id, created=created, team_id=team.team_id)


async def list_prs_for_team(
    db: AsyncSession,
    team_id: uuid.UUID,
    requester_id: uuid.UUID,
) -> tuple[str, list[PRListItem]]:
    membership = await get_membership(db, team_id, requester_id)
    scope = "team" if membership.role == "lead" else "self"

    team_row = await _get_team_or_404(db, team_id)

    member_ids_q = select(TeamMember.user_id).where(TeamMember.team_id == team_id)
    if scope == "self":
        member_ids_q = member_ids_q.where(TeamMember.user_id == requester_id)

    pr_query = (
        select(PullRequest, User.github_id)
        .join(User, User.user_id == PullRequest.user_id)
        .where(
            PullRequest.repository_full_name == team_row.github_repo_full_name,
            PullRequest.user_id.in_(member_ids_q),
        )
        .order_by(PullRequest.submitted_at.desc())
    )
    result = await db.execute(pr_query)
    items: list[PRListItem] = []
    for pr, login in result.all():
        items.append(
            PRListItem(
                id=pr.id,
                user_id=pr.user_id,
                author_login=login or "",
                github_pr_number=pr.github_pr_number,
                github_pr_url=pr.github_pr_url,
                status=pr.status,
                submitted_at=pr.submitted_at,
                is_lgtm=pr.is_lgtm,
            )
        )
    return scope, items
