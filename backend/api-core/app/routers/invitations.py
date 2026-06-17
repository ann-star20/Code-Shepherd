"""팀 초대 라우터 — 수신 목록, 수락/거절."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db import get_session

from ..dependencies import get_current_active_user
from ..services.invite_service import (
    accept_invitation,
    decline_invitation,
    list_pending_for_user,
)

router = APIRouter()


def _parse_user_id(payload: dict) -> uuid.UUID:
    return uuid.UUID(payload["sub"])


def _invitation_json(inv) -> dict:
    return {
        "id": str(inv.id),
        "team_id": str(inv.team_id),
        "team_name": inv.team_name,
        "invitee_user_id": str(inv.invitee_user_id),
        "invited_by_user_id": str(inv.invited_by_user_id),
        "invited_by_login": inv.invited_by_login,
        "invited_by_name": inv.invited_by_name,
        "status": inv.status,
        "created_at": inv.created_at,
    }


@router.get("")
async def list_my_invitations(
    payload: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session),
):
    invitations = await list_pending_for_user(db, _parse_user_id(payload))
    return [_invitation_json(i) for i in invitations]


@router.post("/{invitation_id}/accept")
async def accept_team_invitation(
    invitation_id: uuid.UUID,
    payload: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session),
):
    return await accept_invitation(db, invitation_id, _parse_user_id(payload))


@router.post("/{invitation_id}/decline")
async def decline_team_invitation(
    invitation_id: uuid.UUID,
    payload: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session),
):
    inv = await decline_invitation(db, invitation_id, _parse_user_id(payload))
    return _invitation_json(inv)
