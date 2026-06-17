"""사용자 라우터 — GET /users 검색."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db import get_session

from ..dependencies import get_current_active_user
from ..services.team_service import search_users

router = APIRouter()


@router.get("")
async def list_users(
    search: str = Query(default="", description="login/name 부분일치 검색"),
    payload: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session),
):
    """login/name 부분일치 검색 — 팀원 추가 UI에서 사용. 민감정보 제외."""
    users = await search_users(db, search)
    return [
        {
            "id": str(u.user_id),
            "login": u.login,
            "name": u.name,
            "avatar_url": u.avatar_url,
        }
        for u in users
    ]
