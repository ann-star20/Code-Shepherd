"""팀 라우터 — `users.team` 기반 팀/멤버 API."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db import get_session
from shared.logging import get_logger

from ..dependencies import get_current_active_user
from ..services.team_service import (
    add_member,
    create_team,
    delete_team,
    get_members,
    get_membership,
    get_teams_for_user,
    remove_member,
    update_member_role,
    update_team,
)

router = APIRouter()
logger = get_logger(__name__)


class TeamCreate(BaseModel):
    name: str


class TeamUpdate(BaseModel):
    name: str


class MemberAdd(BaseModel):
    user_id: str
    role: str = "member"


class RoleUpdate(BaseModel):
    role: str


def _parse_user_id(payload: dict) -> uuid.UUID:
    return uuid.UUID(payload["sub"])


@router.get("")
async def list_teams(
    payload: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session),
):
    teams = await get_teams_for_user(db, _parse_user_id(payload))
    return [
        {"id": t.id, "name": t.name, "created_at": t.created_at}
        for t in teams
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_new_team(
    body: TeamCreate,
    payload: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session),
):
    user_id = _parse_user_id(payload)
    team = await create_team(db, body.name, user_id)
    logger.info("team_created", team_id=team.id, creator_id=str(user_id))
    return {"id": team.id, "name": team.name, "created_at": team.created_at}


@router.patch("/{team_id}")
async def patch_team(
    team_id: int,
    body: TeamUpdate,
    payload: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session),
):
    team = await update_team(db, team_id, _parse_user_id(payload), body.name)
    return {"id": team.id, "name": team.name}


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_existing_team(
    team_id: int,
    payload: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session),
):
    await delete_team(db, team_id, _parse_user_id(payload))


@router.get("/{team_id}/members")
async def list_members(
    team_id: int,
    payload: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session),
):
    members = await get_members(db, team_id, _parse_user_id(payload))
    return [
        {
            "id": m.id,
            "user_id": str(m.user_id),
            "role": m.role,
            "joined_at": m.joined_at,
        }
        for m in members
    ]


@router.post("/{team_id}/members", status_code=status.HTTP_201_CREATED)
async def add_team_member(
    team_id: int,
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
        "id": member.id,
        "user_id": str(member.user_id),
        "role": member.role,
    }


@router.delete("/{team_id}/members/{target_user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_team_member(
    team_id: int,
    target_user_id: str,
    payload: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session),
):
    await remove_member(
        db, team_id, _parse_user_id(payload), uuid.UUID(target_user_id)
    )


@router.patch("/{team_id}/members/{target_user_id}")
async def update_team_member_role(
    team_id: int,
    target_user_id: str,
    body: RoleUpdate,
    payload: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session),
):
    member = await update_member_role(
        db,
        team_id,
        _parse_user_id(payload),
        uuid.UUID(target_user_id),
        body.role,
    )
    return {
        "id": member.id,
        "user_id": str(member.user_id),
        "role": member.role,
    }


@router.get("/{team_id}/prs")
async def list_team_prs(
    team_id: int,
    payload: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session),
):
    membership = await get_membership(db, team_id, _parse_user_id(payload))
    return {
        "team_id": team_id,
        "scope": "team" if membership.role == "lead" else "self",
        "prs": [],
        "note": "Actual PR data will be populated by m4",
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
