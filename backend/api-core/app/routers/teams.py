"""팀 라우터 — teams / team_members + GitHub repo."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db import get_session
from shared.logging import get_logger

from ..dependencies import get_current_active_user
from ..services.pr_service import list_prs_for_team
from ..services.team_service import (
    add_member,
    create_team,
    delete_team,
    get_members,
    get_teams_for_user,
    remove_member,
    update_member_role,
    update_team,
)

router = APIRouter()
logger = get_logger(__name__)


class TeamCreate(BaseModel):
    name: str
    github_repo: str = Field(..., description="GitHub repository as owner/repo")


class TeamUpdate(BaseModel):
    name: str | None = None
    github_repo: str | None = None


class MemberAdd(BaseModel):
    user_id: str
    role: str = "member"


class RoleUpdate(BaseModel):
    role: str


def _parse_user_id(payload: dict) -> uuid.UUID:
    return uuid.UUID(payload["sub"])


def _team_json(team) -> dict:
    return {
        "id": str(team.id),
        "name": team.name,
        "github_repo": team.github_repo_full_name,
        "created_at": team.created_at,
    }


@router.get("")
async def list_teams(
    payload: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session),
):
    teams = await get_teams_for_user(db, _parse_user_id(payload))
    return [_team_json(t) for t in teams]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_new_team(
    body: TeamCreate,
    payload: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session),
):
    user_id = _parse_user_id(payload)
    team = await create_team(db, body.name, body.github_repo, user_id)
    logger.info(
        "team_created",
        team_id=str(team.id),
        github_repo=team.github_repo_full_name,
        creator_id=str(user_id),
    )
    return _team_json(team)


@router.patch("/{team_id}")
async def patch_team(
    team_id: uuid.UUID,
    body: TeamUpdate,
    payload: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session),
):
    if body.name is None and body.github_repo is None:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one of name or github_repo is required",
        )
    team = await update_team(
        db,
        team_id,
        _parse_user_id(payload),
        new_name=body.name,
        new_github_repo=body.github_repo,
    )
    return _team_json(team)


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_existing_team(
    team_id: uuid.UUID,
    payload: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session),
):
    await delete_team(db, team_id, _parse_user_id(payload))


@router.get("/{team_id}/members")
async def list_members(
    team_id: uuid.UUID,
    payload: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session),
):
    members = await get_members(db, team_id, _parse_user_id(payload))
    return [
        {
            "id": str(m.id),
            "user_id": str(m.user_id),
            "role": m.role,
            "joined_at": m.joined_at,
        }
        for m in members
    ]


@router.post("/{team_id}/members", status_code=status.HTTP_201_CREATED)
async def add_team_member(
    team_id: uuid.UUID,
    body: MemberAdd,
    payload: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session),
):
    member = await add_member(
        db,
        team_id,
        _parse_user_id(payload),
        uuid.UUID(body.user_id),
        body.role,
    )
    return {
        "id": str(member.id),
        "user_id": str(member.user_id),
        "role": member.role,
    }


@router.delete("/{team_id}/members/{target_user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_team_member(
    team_id: uuid.UUID,
    target_user_id: uuid.UUID,
    payload: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session),
):
    await remove_member(db, team_id, _parse_user_id(payload), target_user_id)


@router.patch("/{team_id}/members/{target_user_id}")
async def update_team_member_role(
    team_id: uuid.UUID,
    target_user_id: uuid.UUID,
    body: RoleUpdate,
    payload: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session),
):
    member = await update_member_role(
        db,
        team_id,
        _parse_user_id(payload),
        target_user_id,
        body.role,
    )
    return {
        "id": str(member.id),
        "user_id": str(member.user_id),
        "role": member.role,
    }


@router.get("/{team_id}/prs")
async def list_team_prs(
    team_id: uuid.UUID,
    payload: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session),
):
    scope, prs = await list_prs_for_team(db, team_id, _parse_user_id(payload))
    return {
        "team_id": str(team_id),
        "scope": scope,
        "prs": [
            {
                "id": str(p.id),
                "user_id": str(p.user_id),
                "author_login": p.author_login,
                "github_pr_number": p.github_pr_number,
                "github_pr_url": p.github_pr_url,
                "status": p.status,
                "submitted_at": p.submitted_at,
                "is_lgtm": p.is_lgtm,
            }
            for p in prs
        ],
    }


@router.post("/prs/{pr_id}/approve")
async def approve_pr(
    pr_id: str,
    payload: dict = Depends(get_current_active_user),
):
    logger.info("pr_approve_stub", pr_id=pr_id, approver_id=payload.get("sub"))
    return {
        "pr_id": pr_id,
        "approved_by": payload.get("sub"),
        "status": "approved",
        "note": "GitHub integration stub — actual approval by m4",
    }
