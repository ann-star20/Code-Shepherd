"""팀 서비스 — 통합 DDL `users.team` 기반 (teams/team_members 테이블 없음)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.user import User
from .team_utils import MemberView, TeamView, member_row_id, team_id_from_name


async def _resolve_team_name(db: AsyncSession, team_id: int) -> str:
    result = await db.execute(
        select(User.team).where(User.team.is_not(None)).distinct()
    )
    for (team_name,) in result.all():
        if team_name and team_id_from_name(team_name) == team_id:
            return team_name
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")


async def _get_user(db: AsyncSession, user_id: uuid.UUID) -> User:
    result = await db.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


async def _team_members(db: AsyncSession, team_name: str) -> list[User]:
    result = await db.execute(
        select(User).where(User.team == team_name).order_by(User.joined_at.asc())
    )
    return list(result.scalars().all())


async def _lead_user_id(db: AsyncSession, team_name: str) -> uuid.UUID:
    members = await _team_members(db, team_name)
    if not members:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    return members[0].user_id


def _member_role(user: User, lead_id: uuid.UUID) -> str:
    return "lead" if user.user_id == lead_id else "member"


def _to_member_view(team_name: str, user: User, lead_id: uuid.UUID) -> MemberView:
    return MemberView(
        id=member_row_id(team_name, user.user_id),
        user_id=user.user_id,
        role=_member_role(user, lead_id),
        joined_at=user.joined_at,
    )


async def get_teams_for_user(db: AsyncSession, user_id: uuid.UUID) -> list[TeamView]:
    user = await _get_user(db, user_id)
    if not user.team:
        return []
    return [
        TeamView(
            id=team_id_from_name(user.team),
            name=user.team,
            created_at=user.joined_at,
        )
    ]


async def get_team_or_404(db: AsyncSession, team_id: int) -> TeamView:
    team_name = await _resolve_team_name(db, team_id)
    members = await _team_members(db, team_name)
    return TeamView(
        id=team_id,
        name=team_name,
        created_at=members[0].joined_at,
    )


async def create_team(db: AsyncSession, name: str, creator_id: uuid.UUID) -> TeamView:
    creator = await _get_user(db, creator_id)
    if creator.team:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already belongs to a team",
        )
    creator.team = name
    await db.commit()
    await db.refresh(creator)
    return TeamView(
        id=team_id_from_name(name),
        name=name,
        created_at=creator.joined_at,
    )


async def update_team(
    db: AsyncSession, team_id: int, requester_id: uuid.UUID, new_name: str
) -> TeamView:
    team_name = await _resolve_team_name(db, team_id)
    await _require_lead(db, team_name, requester_id)
    await db.execute(
        update(User).where(User.team == team_name).values(team=new_name)
    )
    await db.commit()
    members = await _team_members(db, new_name)
    return TeamView(
        id=team_id_from_name(new_name),
        name=new_name,
        created_at=members[0].joined_at,
    )


async def delete_team(db: AsyncSession, team_id: int, requester_id: uuid.UUID) -> None:
    team_name = await _resolve_team_name(db, team_id)
    await _require_lead(db, team_name, requester_id)
    await db.execute(update(User).where(User.team == team_name).values(team=None))
    await db.commit()


async def get_members(
    db: AsyncSession, team_id: int, requester_id: uuid.UUID
) -> list[MemberView]:
    team_name = await _resolve_team_name(db, team_id)
    await _require_member(db, team_name, requester_id)
    lead_id = await _lead_user_id(db, team_name)
    members = await _team_members(db, team_name)
    return [_to_member_view(team_name, m, lead_id) for m in members]


async def add_member(
    db: AsyncSession,
    team_id: int,
    requester_id: uuid.UUID,
    target_user_id: uuid.UUID,
    role: str = "member",
) -> MemberView:
    team_name = await _resolve_team_name(db, team_id)
    await _require_lead(db, team_name, requester_id)

    target = await _get_user(db, target_user_id)
    if target.team == team_name:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a member of this team",
        )
    if target.team and target.team != team_name:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already belongs to another team",
        )

    target.team = team_name
    if role == "lead":
        target.joined_at = datetime.now(UTC) - timedelta(days=3650)
    await db.commit()
    await db.refresh(target)

    lead_id = await _lead_user_id(db, team_name)
    return _to_member_view(team_name, target, lead_id)


async def remove_member(
    db: AsyncSession, team_id: int, requester_id: uuid.UUID, target_user_id: uuid.UUID
) -> None:
    team_name = await _resolve_team_name(db, team_id)
    await _require_lead(db, team_name, requester_id)

    target = await _get_user(db, target_user_id)
    if target.team != team_name:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    lead_id = await _lead_user_id(db, team_name)
    if target.user_id == lead_id:
        members = await _team_members(db, team_name)
        if len(members) <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot remove the last lead from a team",
            )

    target.team = None
    await db.commit()


async def update_member_role(
    db: AsyncSession,
    team_id: int,
    requester_id: uuid.UUID,
    target_user_id: uuid.UUID,
    new_role: str,
) -> MemberView:
    team_name = await _resolve_team_name(db, team_id)
    await _require_lead(db, team_name, requester_id)

    target = await _get_user(db, target_user_id)
    if target.team != team_name:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    lead_id = await _lead_user_id(db, team_name)
    if target.user_id == lead_id and new_role == "member":
        members = await _team_members(db, team_name)
        leads = [m for m in members if _member_role(m, lead_id) == "lead"]
        if len(leads) <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot demote the last lead",
            )
        target.joined_at = datetime.now(UTC)
    elif new_role == "lead":
        min_joined = await db.scalar(
            select(func.min(User.joined_at)).where(User.team == team_name)
        )
        target.joined_at = (min_joined or datetime.now(UTC)) - timedelta(seconds=1)

    await db.commit()
    await db.refresh(target)
    new_lead_id = await _lead_user_id(db, team_name)
    return _to_member_view(team_name, target, new_lead_id)


async def search_users(db: AsyncSession, query: str) -> list[User]:
    pattern = f"%{query}%"
    result = await db.execute(
        select(User)
        .where(
            User.github_id.ilike(pattern)
            | User.name.ilike(pattern)
            | User.email.ilike(pattern)
        )
        .limit(20)
    )
    return list(result.scalars().all())


async def _require_member(db: AsyncSession, team_name: str, user_id: uuid.UUID) -> User:
    user = await _get_user(db, user_id)
    if user.team != team_name:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this team",
        )
    return user


async def _require_lead(db: AsyncSession, team_name: str, user_id: uuid.UUID) -> User:
    user = await _require_member(db, team_name, user_id)
    lead_id = await _lead_user_id(db, team_name)
    if user.user_id != lead_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only team leads can perform this action",
        )
    return user


async def get_membership(
    db: AsyncSession, team_id: int, user_id: uuid.UUID
) -> MemberView:
    team_name = await _resolve_team_name(db, team_id)
    user = await _require_member(db, team_name, user_id)
    lead_id = await _lead_user_id(db, team_name)
    return _to_member_view(team_name, user, lead_id)
