"""api-core 전용 FastAPI 의존성 — 세션 검증 포함 인증."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from shared.auth import get_current_user
from shared.db import get_session

from .services.auth_service import is_session_valid


async def get_current_active_user(
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """JWT 검증 + 세션 취소 여부 확인.

    logout 후 동일 토큰 재사용을 막기 위해 DB 세션도 체크한다.
    """
    jti = payload.get("jti")
    if jti:
        valid = await is_session_valid(db, jti)
        if not valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session has been revoked",
                headers={"WWW-Authenticate": "Bearer"},
            )
    return payload
