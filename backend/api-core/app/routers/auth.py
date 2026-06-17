"""인증 라우터 — GitHub OAuth authorize/callback, /me, logout, refresh."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from shared.auth import decode_token
from shared.config import get_settings
from shared.db import get_session
from shared.logging import get_logger

from ..dependencies import get_current_active_user
from ..services.auth_service import (
    create_session,
    github_exchange_code,
    github_get_user_profile,
    issue_tokens,
    revoke_session,
    upsert_user,
)

router = APIRouter()
logger = get_logger(__name__)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


@router.get("/authorize")
async def github_authorize():
    """GitHub OAuth 시작 — authorization URL로 리다이렉트."""
    settings = get_settings()
    from urllib.parse import quote

    redirect_uri = quote(settings.github_oauth_redirect_uri, safe="")
    authorize_url = (
        "https://github.com/login/oauth/authorize"
        f"?client_id={settings.github_oauth_client_id}"
        f"&redirect_uri={redirect_uri}"
        "&scope=read:user"
    )
    return RedirectResponse(url=authorize_url)


@router.get("/callback", response_model=TokenResponse)
@router.get("/github/callback", response_model=TokenResponse)
async def github_callback(
    code: str,
    db: AsyncSession = Depends(get_session),
):
    """GitHub OAuth 콜백 — code → access_token → 프로필 → upsert → JWT 발급."""
    try:
        token_data = await github_exchange_code(code)
    except Exception as exc:
        logger.exception("github_token_exchange_failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub token exchange failed",
        ) from exc

    if "error" in token_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=token_data.get("error_description", token_data.get("error", "OAuth error")),
        )

    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No access token in response",
        )

    try:
        profile = await github_get_user_profile(access_token)
        user = await upsert_user(db, profile)
    except Exception as exc:
        logger.exception("oauth_callback_persist_failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save user after GitHub login",
        ) from exc

    tokens = issue_tokens(user)
    await create_session(db, user.user_id, tokens["jti"])

    logger.info("user_logged_in", user_id=str(user.user_id), login=user.login)
    return TokenResponse(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
    )


@router.get("/me")
async def get_me(
    payload: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session),
):
    """현재 인증된 사용자 정보."""
    from ..models.user import User
    from sqlalchemy import select

    user_id = uuid.UUID(payload["sub"])
    result = await db.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return {
        "id": str(user.user_id),
        "login": user.login,
        "name": user.name,
        "avatar_url": user.avatar_url,
        "team": user.team,
        "skill_level": user.skill_level,
        "created_at": user.joined_at,
    }


@router.post("/logout")
async def logout(
    payload: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session),
):
    """현재 세션 무효화 — 이후 같은 토큰으로 보호 라우트 접근 시 401."""
    jti = payload.get("jti")
    if jti:
        await revoke_session(db, jti)
    logger.info("user_logged_out", user_id=payload.get("sub"))
    return {"detail": "Logged out successfully"}


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_session),
):
    """refresh 토큰으로 새 access 토큰 발급."""
    try:
        payload = decode_token(body.refresh_token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not a refresh token",
        )

    from ..models.user import User
    from sqlalchemy import select

    user_id = uuid.UUID(payload["sub"])
    result = await db.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    tokens = issue_tokens(user)
    await create_session(db, user.user_id, tokens["jti"])
    return TokenResponse(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
    )
