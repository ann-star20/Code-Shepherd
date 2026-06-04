"""팀 라우터 — 팀 CRUD, 멤버 관리, PR 현황(스텁), 승인(가드)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db import get_session

from ..dependencies import get_current_active_user
from shared.logging import get_logger

from ..services.team_service import (
    add_member,
    create_team,
    delete_team,
    get_members,
    get_team_or_404,
    get_teams_for_user,
    remove_member,
    update_member_role,
    update_team,
    _require_lead,
    _require_member,
)

router = APIRouter()
logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 요청/응답 스키마
# ---------------------------------------------------------------------------

class TeamCreate(BaseModel):
    name: str


class TeamUpdate(BaseModel):
    name: str


class MemberAdd(BaseModel):
    user_id: int
    role: str = "member"


class RoleUpdate(BaseModel):
    role: str  # "lead" | "member"


# ---------------------------------------------------------------------------
# 팀 엔드포인트
# ---------------------------------------------------------------------------

@router.get("")
async def list_teams(
    payload: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session),
):
    """내가 속한 팀만 반환."""
    user_id = int(payload["sub"])
    teams = await get_teams_for_user(db, user_id)
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
    """팀 생성 — 생성자는 자동으로 lead 등록."""
    user_id = int(payload["sub"])
    team = await create_team(db, body.name, user_id)
    logger.info("team_created", team_id=team.id, creator_id=user_id)
    return {"id": team.id, "name": team.name, "created_at": team.created_at}


@router.patch("/{team_id}")
async def patch_team(
    team_id: int,
    body: TeamUpdate,
    payload: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session),
):
    """팀 정보 수정 — lead만."""
    user_id = int(payload["sub"])
    team = await update_team(db, team_id, user_id, body.name)
    return {"id": team.id, "name": team.name}


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_existing_team(
    team_id: int,
    payload: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session),
):
    """팀 삭제 (soft) — lead만."""
    user_id = int(payload["sub"])
    await delete_team(db, team_id, user_id)


# ---------------------------------------------------------------------------
# 멤버 엔드포인트
# ---------------------------------------------------------------------------

@router.get("/{team_id}/members")
async def list_members(
    team_id: int,
    payload: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session),
):
    """멤버 목록 — 팀 소속이면 조회 가능."""
    user_id = int(payload["sub"])
    members = await get_members(db, team_id, user_id)
    return [
        {"id": m.id, "user_id": m.user_id, "role": m.role, "joined_at": m.joined_at}
        for m in members
    ]


@router.post("/{team_id}/members", status_code=status.HTTP_201_CREATED)
async def add_team_member(
    team_id: int,
    body: MemberAdd,
    payload: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session),
):
    """멤버 추가 — lead만."""
    user_id = int(payload["sub"])
    member = await add_member(db, team_id, user_id, body.user_id, body.role)
    return {"id": member.id, "user_id": member.user_id, "role": member.role}


@router.delete("/{team_id}/members/{target_user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_team_member(
    team_id: int,
    target_user_id: int,
    payload: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session),
):
    """멤버 제거 — lead만. 마지막 lead 제거 거부."""
    user_id = int(payload["sub"])
    await remove_member(db, team_id, user_id, target_user_id)


@router.patch("/{team_id}/members/{target_user_id}")
async def update_team_member_role(
    team_id: int,
    target_user_id: int,
    body: RoleUpdate,
    payload: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session),
):
    """역할 변경 — lead만."""
    user_id = int(payload["sub"])
    member = await update_member_role(db, team_id, user_id, target_user_id, body.role)
    return {"id": member.id, "user_id": member.user_id, "role": member.role}


# ---------------------------------------------------------------------------
# PR 엔드포인트 (권한 가드 실제, 데이터는 스텁)
# ---------------------------------------------------------------------------

@router.get("/{team_id}/prs")
async def list_team_prs(
    team_id: int,
    payload: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session),
):
    """팀 PR 현황 — lead는 팀 전체, member는 본인 것만. 데이터는 빈 목록(m4 몫)."""
    user_id = int(payload["sub"])
    membership = await _require_member(db, team_id, user_id)

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
    db: AsyncSession = Depends(get_session),
):
    """PR 승인 — 권한 가드만 실제, GitHub 반영은 스텁.
    
    Note: 이 엔드포인트는 특정 팀 컨텍스트 없이 호출됨.
    실제 구현에서는 PR이 속한 팀을 확인해 lead 권한을 검증해야 함.
    현재는 인증된 사용자면 통과 (베이스라인 스텁).
    """
    user_id = int(payload["sub"])
    logger.info("pr_approve_stub", pr_id=pr_id, approver_id=user_id)
    return {
        "pr_id": pr_id,
        "approved_by": user_id,
        "status": "approved",
        "note": "GitHub integration stub — actual approval by m4",
    }
