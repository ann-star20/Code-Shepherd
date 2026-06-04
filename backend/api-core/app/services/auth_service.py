"""인증 서비스 — GitHub OAuth, JWT 발급, 세션 관리."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.auth import create_access_token, create_refresh_token
from shared.config import get_settings

from ..models.session import AuthSession
from ..models.user import User


async def github_exchange_code(code: str) -> dict:
    """GitHub OAuth code를 access_token으로 교환."""
    settings = get_settings()
    data = {
        "client_id": settings.github_oauth_client_id,
        "client_secret": settings.github_oauth_client_secret,
        "code": code,
        "redirect_uri": settings.github_oauth_redirect_uri,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://github.com/login/oauth/access_token",
            data=data,
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()


async def github_get_user_profile(access_token: str) -> dict:
    """GitHub access_token으로 사용자 프로필 조회."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def upsert_user(session: AsyncSession, github_profile: dict) -> User:
    """GitHub 프로필로 통합 DDL `users` 테이블에 upsert."""
    github_login = github_profile["login"]
    result = await session.execute(
        select(User).where(User.github_id == github_login)
    )
    user = result.scalar_one_or_none()
    display_name = github_profile.get("name") or github_login

    if user is None:
        user = User(
            github_id=github_login,
            name=display_name,
            email=github_profile.get("email"),
            github_url=github_profile.get("avatar_url") or github_profile.get("html_url"),
            diagnosis_source="github",
        )
        session.add(user)
    else:
        user.name = display_name
        if github_profile.get("email"):
            user.email = github_profile["email"]
        profile_url = github_profile.get("avatar_url") or github_profile.get("html_url")
        if profile_url:
            user.github_url = profile_url

    await session.commit()
    await session.refresh(user)
    return user


def issue_tokens(user: User) -> dict[str, str]:
    """access + refresh 토큰 쌍 발급."""
    jti = str(uuid.uuid4())
    access = create_access_token(
        subject=user.user_id,
        extra_claims={"jti": jti, "login": user.login},
    )
    refresh = create_refresh_token(subject=user.user_id)
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "jti": jti,
    }


async def create_session(
    db_session: AsyncSession, user_id: uuid.UUID, jti: str
) -> AuthSession:
    settings = get_settings()
    expires_at = datetime.now(UTC) + timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )
    sess = AuthSession(user_id=user_id, token_jti=jti, expires_at=expires_at)
    db_session.add(sess)
    await db_session.commit()
    return sess


async def revoke_session(db_session: AsyncSession, jti: str) -> bool:
    result = await db_session.execute(
        select(AuthSession).where(AuthSession.token_jti == jti)
    )
    sess = result.scalar_one_or_none()
    if sess is None:
        return False
    sess.is_revoked = True
    await db_session.commit()
    return True


async def is_session_valid(db_session: AsyncSession, jti: str) -> bool:
    result = await db_session.execute(
        select(AuthSession).where(
            AuthSession.token_jti == jti,
            AuthSession.is_revoked.is_(False),
        )
    )
    return result.scalar_one_or_none() is not None
