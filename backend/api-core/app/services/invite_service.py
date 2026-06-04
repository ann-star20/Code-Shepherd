"""팀 초대 — pending → accept/decline, 수락 시 team_members 생성."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.invitation import TeamInvitation
from ..models.team import Team, TeamMember
from ..models.user import User
from .team_service import (
    _get_team_or_404,
    _get_user,
    _require_lead,
    _to_member_view,
    _user_membership,
    join_team_member,
)
from .team_utils import InvitationView


def _to_invitation_view(
    inv: TeamInvitation,
    *,
    team_name: str,
    inviter: User,
) -> InvitationView:
    return InvitationView(
        id=inv.id,
        team_id=inv.team_id,
        team_name=team_name,
        invitee_user_id=inv.invitee_user_id,
        invited_by_user_id=inv.invited_by_user_id,
        invited_by_login=inviter.login,
        invited_by_name=inviter.name,
        status=inv.status,
        created_at=inv.created_at,
    )


async def _get_user_by_github_id(db: AsyncSession, github_id: str) -> User:
    normalized = github_id.strip().lower()
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="github_id is required",
        )
    result = await db.execute(
        select(User).where(func.lower(User.github_id) == normalized)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No user registered with this GitHub account",
        )
    return user


async def _assert_can_invite(
    db: AsyncSession,
    team_id: uuid.UUID,
    invitee_id: uuid.UUID,
    requester_id: uuid.UUID,
) -> tuple[Team, User]:
    team = await _get_team_or_404(db, team_id)
    await _require_lead(db, team_id, requester_id)

    if invitee_id == requester_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot invite yourself",
        )

    invitee = await _get_user(db, invitee_id)

    if await _user_membership(db, team_id, invitee_id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a member of this team",
        )

    other_team = await db.execute(
        select(TeamMember).where(TeamMember.user_id == invitee_id)
    )
    if other_team.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already belongs to another team",
        )

    pending = await db.execute(
        select(TeamInvitation).where(
            TeamInvitation.team_id == team_id,
            TeamInvitation.invitee_user_id == invitee_id,
            TeamInvitation.status == "pending",
        )
    )
    if pending.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A pending invitation already exists for this user",
        )

    return team, invitee


async def create_invitation(
    db: AsyncSession,
    team_id: uuid.UUID,
    requester_id: uuid.UUID,
    *,
    target_user_id: uuid.UUID | None = None,
    github_id: str | None = None,
) -> InvitationView:
    if target_user_id is None and github_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Either user_id or github_id is required",
        )

    if target_user_id is None:
        invitee = await _get_user_by_github_id(db, github_id or "")
        target_user_id = invitee.user_id

    team, _ = await _assert_can_invite(db, team_id, target_user_id, requester_id)
    inviter = await _get_user(db, requester_id)

    invitation = TeamInvitation(
        team_id=team_id,
        invitee_user_id=target_user_id,
        invited_by_user_id=requester_id,
        status="pending",
    )
    db.add(invitation)
    await db.commit()
    await db.refresh(invitation)
    return _to_invitation_view(invitation, team_name=team.name, inviter=inviter)


async def list_pending_for_user(
    db: AsyncSession, user_id: uuid.UUID
) -> list[InvitationView]:
    result = await db.execute(
        select(TeamInvitation, Team, User)
        .join(Team, Team.team_id == TeamInvitation.team_id)
        .join(User, User.user_id == TeamInvitation.invited_by_user_id)
        .where(
            TeamInvitation.invitee_user_id == user_id,
            TeamInvitation.status == "pending",
        )
        .order_by(TeamInvitation.created_at.desc())
    )
    rows = result.all()
    return [
        _to_invitation_view(inv, team_name=team.name, inviter=inviter)
        for inv, team, inviter in rows
    ]


async def _get_pending_invitation(
    db: AsyncSession, invitation_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[TeamInvitation, Team, User]:
    result = await db.execute(
        select(TeamInvitation, Team, User)
        .join(Team, Team.team_id == TeamInvitation.team_id)
        .join(User, User.user_id == TeamInvitation.invited_by_user_id)
        .where(TeamInvitation.id == invitation_id)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found"
        )
    inv, team, inviter = row
    if inv.invitee_user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    if inv.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Invitation is no longer pending",
        )
    return inv, team, inviter


async def accept_invitation(
    db: AsyncSession, invitation_id: uuid.UUID, user_id: uuid.UUID
) -> dict:
    inv, team, _inviter = await _get_pending_invitation(db, invitation_id, user_id)
    inv.status = "accepted"
    inv.responded_at = datetime.now(UTC)
    await join_team_member(db, team.team_id, inv.invitee_user_id, role="member")
    await db.commit()
    membership = await _user_membership(db, team.team_id, inv.invitee_user_id)
    assert membership is not None
    user = await _get_user(db, inv.invitee_user_id)
    member_view = _to_member_view(membership, user)
    return {
        "invitation_id": str(inv.id),
        "team_id": str(team.team_id),
        "member": {
            "id": str(member_view.id),
            "user_id": str(member_view.user_id),
            "role": member_view.role,
            "login": member_view.login,
            "name": member_view.name,
            "avatar_url": member_view.avatar_url,
        },
    }


async def decline_invitation(
    db: AsyncSession, invitation_id: uuid.UUID, user_id: uuid.UUID
) -> InvitationView:
    inv, team, inviter = await _get_pending_invitation(db, invitation_id, user_id)
    inv.status = "declined"
    inv.responded_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(inv)
    return _to_invitation_view(inv, team_name=team.name, inviter=inviter)
