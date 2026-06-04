"""인증 서비스 — GitHub OAuth, JWT 발급, 세션 관리."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.auth import create_access_token, create_refresh_token, decode_token
from shared.config import get_settings

from ..models.session import UserSession
from ..models.user import User


async def github_exchange_code(code: str) -> dict:
    """GitHub OAuth code를 access_token으로 교환."""
    settings = get_settings()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": settings.github_oauth_client_id,
                "client_secret": settings.github_oauth_client_secret,
                "code": code,
            },
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
    """GitHub 프로필로 users 테이블에 upsert."""
    result = await session.execute(
        select(User).where(User.github_id == github_profile["id"])
    )
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            github_id=github_profile["id"],
            login=github_profile["login"],
            name=github_profile.get("name"),
            avatar_url=github_profile.get("avatar_url"),
        )
        session.add(user)
    else:
        user.login = github_profile["login"]
        user.name = github_profile.get("name")
        user.avatar_url = github_profile.get("avatar_url")
    await session.commit()
    await session.refresh(user)
    return user


def issue_tokens(user: User) -> dict[str, str]:
    """access + refresh 토큰 쌍 발급. JTI는 세션 관리에 사용."""
    jti = str(uuid.uuid4())
    access = create_access_token(
        subject=user.id,
        extra_claims={"jti": jti, "login": user.login},
    )
    refresh = create_refresh_token(subject=user.id)
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer", "jti": jti}


async def create_session(
    db_session: AsyncSession, user_id: int, jti: str
) -> UserSession:
    """새 세션 레코드 생성."""
    settings = get_settings()
    expires_at = datetime.now(UTC) + timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )
    sess = UserSession(user_id=user_id, token_jti=jti, expires_at=expires_at)
    db_session.add(sess)
    await db_session.commit()
    return sess


async def revoke_session(db_session: AsyncSession, jti: str) -> bool:
    """세션 무효화 (로그아웃). 세션이 없으면 False 반환."""
    result = await db_session.execute(
        select(UserSession).where(UserSession.token_jti == jti)
    )
    sess = result.scalar_one_or_none()
    if sess is None:
        return False
    sess.is_revoked = True
    await db_session.commit()
    return True


async def is_session_valid(db_session: AsyncSession, jti: str) -> bool:
    """세션이 유효한지(존재 & 미취소) 확인."""
    result = await db_session.execute(
        select(UserSession).where(
            UserSession.token_jti == jti,
            UserSession.is_revoked.is_(False),
        )
    )
    return result.scalar_one_or_none() is not None
