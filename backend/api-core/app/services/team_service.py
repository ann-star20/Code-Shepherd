"""팀 서비스 — 팀 CRUD, 멤버 관리, 권한 검증."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.team import Team, TeamMember
from ..models.user import User


# ---------------------------------------------------------------------------
# 팀 조회
# ---------------------------------------------------------------------------

async def get_teams_for_user(db: AsyncSession, user_id: int) -> list[Team]:
    """내가 속한 팀만 반환."""
    result = await db.execute(
        select(Team)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(TeamMember.user_id == user_id, Team.is_deleted.is_(False))
    )
    return list(result.scalars().all())


async def get_team_or_404(db: AsyncSession, team_id: int) -> Team:
    result = await db.execute(
        select(Team).where(Team.id == team_id, Team.is_deleted.is_(False))
    )
    team = result.scalar_one_or_none()
    if team is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    return team


# ---------------------------------------------------------------------------
# 팀 생성/수정/삭제
# ---------------------------------------------------------------------------

async def create_team(db: AsyncSession, name: str, creator_id: int) -> Team:
    """팀 생성 — 생성자는 자동으로 lead로 등록."""
    team = Team(name=name)
    db.add(team)
    await db.flush()  # team.id 확보

    member = TeamMember(team_id=team.id, user_id=creator_id, role="lead")
    db.add(member)
    await db.commit()
    await db.refresh(team)
    return team


async def update_team(db: AsyncSession, team_id: int, requester_id: int, name: str) -> Team:
    """팀 정보 수정 — lead만 가능."""
    await _require_lead(db, team_id, requester_id)
    team = await get_team_or_404(db, team_id)
    team.name = name
    await db.commit()
    await db.refresh(team)
    return team


async def delete_team(db: AsyncSession, team_id: int, requester_id: int) -> None:
    """팀 소프트 삭제 — lead만 가능."""
    await _require_lead(db, team_id, requester_id)
    team = await get_team_or_404(db, team_id)
    team.is_deleted = True
    await db.commit()


# ---------------------------------------------------------------------------
# 멤버 관리
# ---------------------------------------------------------------------------

async def get_members(db: AsyncSession, team_id: int, requester_id: int) -> list[TeamMember]:
    """멤버 목록 — 팀 소속이면 조회 가능."""
    await _require_member(db, team_id, requester_id)
    result = await db.execute(
        select(TeamMember).where(TeamMember.team_id == team_id)
    )
    return list(result.scalars().all())


async def add_member(
    db: AsyncSession, team_id: int, requester_id: int, user_id: int, role: str = "member"
) -> TeamMember:
    """멤버 추가 — lead만, 중복 방지."""
    await _require_lead(db, team_id, requester_id)

    # 중복 확인
    result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id, TeamMember.user_id == user_id
        )
    )
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a member of this team",
        )

    member = TeamMember(team_id=team_id, user_id=user_id, role=role)
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return member


async def remove_member(
    db: AsyncSession, team_id: int, requester_id: int, user_id: int
) -> None:
    """멤버 제거 — lead만. 마지막 lead 제거 거부."""
    await _require_lead(db, team_id, requester_id)

    result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id, TeamMember.user_id == user_id
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    # 마지막 lead 제거 방지
    if member.role == "lead":
        leads = await _count_leads(db, team_id)
        if leads <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot remove the last lead from a team",
            )

    await db.delete(member)
    await db.commit()


async def update_member_role(
    db: AsyncSession, team_id: int, requester_id: int, user_id: int, new_role: str
) -> TeamMember:
    """멤버 역할 변경 — lead만. lead→member 시 마지막 lead 방지."""
    await _require_lead(db, team_id, requester_id)

    result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id, TeamMember.user_id == user_id
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    if member.role == "lead" and new_role == "member":
        leads = await _count_leads(db, team_id)
        if leads <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot demote the last lead",
            )

    member.role = new_role
    await db.commit()
    await db.refresh(member)
    return member


# ---------------------------------------------------------------------------
# 사용자 검색
# ---------------------------------------------------------------------------

async def search_users(db: AsyncSession, query: str) -> list[User]:
    """login/name 부분일치 검색."""
    result = await db.execute(
        select(User).where(
            User.login.ilike(f"%{query}%") | User.name.ilike(f"%{query}%")
        ).limit(20)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# 권한 헬퍼
# ---------------------------------------------------------------------------

async def _get_membership(
    db: AsyncSession, team_id: int, user_id: int
) -> TeamMember | None:
    result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id, TeamMember.user_id == user_id
        )
    )
    return result.scalar_one_or_none()


async def _require_member(db: AsyncSession, team_id: int, user_id: int) -> TeamMember:
    membership = await _get_membership(db, team_id, user_id)
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this team",
        )
    return membership


async def _require_lead(db: AsyncSession, team_id: int, user_id: int) -> TeamMember:
    membership = await _require_member(db, team_id, user_id)
    if membership.role != "lead":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only team leads can perform this action",
        )
    return membership


async def _count_leads(db: AsyncSession, team_id: int) -> int:
    result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id, TeamMember.role == "lead"
        )
    )
    return len(result.scalars().all())
