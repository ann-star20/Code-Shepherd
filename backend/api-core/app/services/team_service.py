"""팀 서비스 — teams / team_members SSOT, users.team 동기화."""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.team import Team, TeamMember
from ..models.user import User
from .team_utils import MemberView, TeamView, normalize_github_repo


async def _get_user(db: AsyncSession, user_id: uuid.UUID) -> User:
    result = await db.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


async def _get_team_or_404(db: AsyncSession, team_id: uuid.UUID) -> Team:
    result = await db.execute(select(Team).where(Team.team_id == team_id))
    team = result.scalar_one_or_none()
    if team is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    return team


def _to_team_view(team: Team) -> TeamView:
    return TeamView(
        id=team.team_id,
        name=team.name,
        github_repo_full_name=team.github_repo_full_name,
        created_at=team.created_at,
    )


def _to_member_view(member: TeamMember, user: User) -> MemberView:
    return MemberView(
        id=member.id,
        user_id=member.user_id,
        role=member.team_role,
        joined_at=member.joined_at,
        login=user.login,
        name=user.name,
        avatar_url=user.avatar_url,
    )


async def _user_membership(
    db: AsyncSession, team_id: uuid.UUID, user_id: uuid.UUID
) -> TeamMember | None:
    result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def _sync_users_team_name(
    db: AsyncSession, team_id: uuid.UUID, team_name: str
) -> None:
    member_ids = await db.scalars(
        select(TeamMember.user_id).where(TeamMember.team_id == team_id)
    )
    for uid in member_ids.all():
        await db.execute(update(User).where(User.user_id == uid).values(team=team_name))


async def _clear_users_team_for_team(db: AsyncSession, team_name: str) -> None:
    await db.execute(update(User).where(User.team == team_name).values(team=None))


async def get_teams_for_user(db: AsyncSession, user_id: uuid.UUID) -> list[TeamView]:
    result = await db.execute(
        select(Team)
        .join(TeamMember, TeamMember.team_id == Team.team_id)
        .where(TeamMember.user_id == user_id)
        .order_by(Team.created_at.asc())
    )
    return [_to_team_view(t) for t in result.scalars().all()]


async def get_team_or_404(db: AsyncSession, team_id: uuid.UUID) -> TeamView:
    team = await _get_team_or_404(db, team_id)
    return _to_team_view(team)


async def create_team(
    db: AsyncSession, name: str, github_repo: str, creator_id: uuid.UUID
) -> TeamView:
    team_name = name.strip()
    if not team_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Team name is required",
        )

    try:
        repo = normalize_github_repo(github_repo)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    creator = await _get_user(db, creator_id)

    existing_membership = await db.execute(
        select(TeamMember).where(TeamMember.user_id == creator_id)
    )
    if existing_membership.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already belongs to a team",
        )

    team = Team(name=team_name, github_repo_full_name=repo)
    db.add(team)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Team name or GitHub repository already registered",
        ) from exc

    membership = TeamMember(
        team_id=team.team_id,
        user_id=creator_id,
        team_role="lead",
    )
    db.add(membership)
    creator.team = team_name
    await db.commit()
    await db.refresh(team)
    return _to_team_view(team)


async def update_team(
    db: AsyncSession,
    team_id: uuid.UUID,
    requester_id: uuid.UUID,
    *,
    new_name: str | None = None,
    new_github_repo: str | None = None,
) -> TeamView:
    team = await _get_team_or_404(db, team_id)
    await _require_lead(db, team_id, requester_id)

    if new_name is not None:
        stripped = new_name.strip()
        if not stripped:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Team name is required",
            )
        team.name = stripped

    if new_github_repo is not None:
        try:
            team.github_repo_full_name = normalize_github_repo(new_github_repo)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc

    try:
        await db.flush()
        await _sync_users_team_name(db, team_id, team.name)
        await db.commit()
        await db.refresh(team)
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Team name or GitHub repository already registered",
        ) from exc

    return _to_team_view(team)


async def delete_team(
    db: AsyncSession, team_id: uuid.UUID, requester_id: uuid.UUID
) -> None:
    team = await _get_team_or_404(db, team_id)
    await _require_lead(db, team_id, requester_id)
    await _clear_users_team_for_team(db, team.name)
    await db.execute(delete(Team).where(Team.team_id == team_id))
    await db.commit()


async def get_members(
    db: AsyncSession, team_id: uuid.UUID, requester_id: uuid.UUID
) -> list[MemberView]:
    await _get_team_or_404(db, team_id)
    await _require_member(db, team_id, requester_id)
    result = await db.execute(
        select(TeamMember, User)
        .join(User, User.user_id == TeamMember.user_id)
        .where(TeamMember.team_id == team_id)
        .order_by(TeamMember.joined_at.asc())
    )
    return [_to_member_view(m, u) for m, u in result.all()]


async def join_team_member(
    db: AsyncSession,
    team_id: uuid.UUID,
    target_user_id: uuid.UUID,
    role: str = "member",
) -> MemberView:
    """초대 수락 등 — 팀장 검증 없이 멤버십 생성."""
    team = await _get_team_or_404(db, team_id)

    if role not in ("lead", "member"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="role must be 'lead' or 'member'",
        )

    target = await _get_user(db, target_user_id)

    existing = await db.execute(
        select(TeamMember).where(TeamMember.user_id == target_user_id)
    )
    existing_row = existing.scalar_one_or_none()
    if existing_row is not None:
        if existing_row.team_id == team_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User is already a member of this team",
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already belongs to another team",
        )

    membership = TeamMember(
        team_id=team_id,
        user_id=target_user_id,
        team_role=role,
    )
    db.add(membership)
    target.team = team.name
    await db.flush()
    await db.refresh(membership)
    return _to_member_view(membership, target)


async def add_member(
    db: AsyncSession,
    team_id: uuid.UUID,
    requester_id: uuid.UUID,
    target_user_id: uuid.UUID,
    role: str = "member",
) -> MemberView:
    """테스트·레거시 — 즉시 가입 (초대 플로우는 invite_service)."""
    await _require_lead(db, team_id, requester_id)
    view = await join_team_member(db, team_id, target_user_id, role)
    await db.commit()
    return view


async def remove_member(
    db: AsyncSession, team_id: uuid.UUID, requester_id: uuid.UUID, target_user_id: uuid.UUID
) -> None:
    await _get_team_or_404(db, team_id)
    await _require_lead(db, team_id, requester_id)

    membership = await _user_membership(db, team_id, target_user_id)
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    if membership.team_role == "lead":
        result = await db.execute(
            select(TeamMember).where(
                TeamMember.team_id == team_id, TeamMember.team_role == "lead"
            )
        )
        if len(result.scalars().all()) <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot remove the last lead from a team",
            )

    target = await _get_user(db, target_user_id)
    await db.delete(membership)
    target.team = None
    await db.commit()


async def update_member_role(
    db: AsyncSession,
    team_id: uuid.UUID,
    requester_id: uuid.UUID,
    target_user_id: uuid.UUID,
    new_role: str,
) -> MemberView:
    await _get_team_or_404(db, team_id)
    await _require_lead(db, team_id, requester_id)

    if new_role not in ("lead", "member"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="role must be 'lead' or 'member'",
        )

    membership = await _user_membership(db, team_id, target_user_id)
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    if membership.team_role == "lead" and new_role == "member":
        result = await db.execute(
            select(TeamMember).where(
                TeamMember.team_id == team_id, TeamMember.team_role == "lead"
            )
        )
        if len(result.scalars().all()) <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot demote the last lead",
            )

    membership.team_role = new_role
    await db.commit()
    await db.refresh(membership)
    user = await _get_user(db, target_user_id)
    return _to_member_view(membership, user)


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


async def _require_member(
    db: AsyncSession, team_id: uuid.UUID, user_id: uuid.UUID
) -> TeamMember:
    membership = await _user_membership(db, team_id, user_id)
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this team",
        )
    return membership


async def _require_lead(
    db: AsyncSession, team_id: uuid.UUID, user_id: uuid.UUID
) -> TeamMember:
    membership = await _require_member(db, team_id, user_id)
    if membership.team_role != "lead":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only team leads can perform this action",
        )
    return membership


async def get_membership(
    db: AsyncSession, team_id: uuid.UUID, user_id: uuid.UUID
) -> MemberView:
    await _get_team_or_404(db, team_id)
    membership = await _require_member(db, team_id, user_id)
    user = await _get_user(db, user_id)
    return _to_member_view(membership, user)
