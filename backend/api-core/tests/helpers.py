"""테스트 헬퍼 — 통합 DDL users + auth_sessions."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from shared.auth import create_access_token

from app.models.session import AuthSession
from app.models.user import User


async def make_user(db_session, *, login: str, github_id: str | None = None) -> User:
    user = User(
        user_id=uuid.uuid4(),
        github_id=github_id or login,
        name=login.capitalize(),
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def make_token(db_session, user: User) -> tuple[str, str]:
    jti = str(uuid.uuid4())
    token = create_access_token(
        subject=user.user_id,
        extra_claims={"jti": jti, "login": user.login},
    )
    sess = AuthSession(
        user_id=user.user_id,
        token_jti=jti,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(sess)
    await db_session.commit()
    return token, jti
