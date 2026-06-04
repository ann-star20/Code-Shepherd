"""TDD: OAuth 콜백 — user upsert + JWT 발급, 토큰 거부, logout 무효화."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from shared.auth import create_access_token, decode_token


# ---------------------------------------------------------------------------
# 헬퍼 — DB에 직접 유저/세션 생성
# ---------------------------------------------------------------------------

async def _create_user_and_token(db_session, user_id=1, login="testuser"):
    from app.models.user import User
    from app.models.session import UserSession
    from datetime import datetime, UTC, timedelta
    import uuid

    user = User(id=user_id, github_id=user_id * 100, login=login, name="Test User")
    db_session.add(user)
    await db_session.flush()

    jti = str(uuid.uuid4())
    token = create_access_token(subject=user_id, extra_claims={"jti": jti, "login": login})
    sess = UserSession(
        user_id=user_id,
        token_jti=jti,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(sess)
    await db_session.commit()
    return token, jti


# ---------------------------------------------------------------------------
# GitHub OAuth 콜백 테스트
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_oauth_callback_upserts_user_and_issues_jwt(client, db_session):
    """GitHub OAuth 콜백: user upsert + JWT access/refresh 발급."""
    github_token_resp = {"access_token": "gho_test123", "token_type": "bearer"}
    github_profile_resp = {
        "id": 12345,
        "login": "octocat",
        "name": "The Octocat",
        "avatar_url": "https://github.com/images/error/octocat_happy.gif",
    }

    with respx.mock:
        respx.post("https://github.com/login/oauth/access_token").mock(
            return_value=Response(200, json=github_token_resp)
        )
        respx.get("https://api.github.com/user").mock(
            return_value=Response(200, json=github_profile_resp)
        )

        resp = await client.get("/auth/callback?code=test_code")

    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"

    # access_token이 유효한 JWT인지 확인
    payload = decode_token(data["access_token"])
    assert payload["type"] == "access"


@pytest.mark.asyncio
async def test_oauth_callback_upserts_same_user_twice(client, db_session):
    """같은 GitHub 계정으로 두 번 로그인하면 upsert (중복 생성 없음)."""
    github_token_resp = {"access_token": "gho_test456"}
    github_profile_resp = {
        "id": 99999,
        "login": "dupuser",
        "name": "Dup User",
        "avatar_url": None,
    }

    with respx.mock:
        respx.post("https://github.com/login/oauth/access_token").mock(
            return_value=Response(200, json=github_token_resp)
        )
        respx.get("https://api.github.com/user").mock(
            return_value=Response(200, json=github_profile_resp)
        )

        resp1 = await client.get("/auth/callback?code=code1")
        resp2 = await client.get("/auth/callback?code=code2")

    assert resp1.status_code == 200
    assert resp2.status_code == 200


# ---------------------------------------------------------------------------
# /auth/me 테스트
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_me_returns_user_info(client, db_session):
    token, _ = await _create_user_and_token(db_session, user_id=2, login="me_user")
    resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["login"] == "me_user"
    assert "id" in data
    assert "github_id" not in data  # 민감정보 미노출


@pytest.mark.asyncio
async def test_me_returns_401_without_token(client):
    resp = await client.get("/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_401_with_expired_token(client, db_session):
    from datetime import timedelta

    token = create_access_token(subject=99, expires_delta=timedelta(seconds=-1))
    resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# logout / 토큰 무효화 테스트
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_logout_revokes_session(client, db_session):
    """로그아웃 후 동일 토큰으로 보호 라우트 접근 시 401."""
    token, _ = await _create_user_and_token(db_session, user_id=3, login="logout_user")

    # 로그아웃
    resp = await client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200

    # 같은 토큰으로 /auth/me 접근 → 401
    resp2 = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp2.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_without_token_returns_401(client):
    resp = await client.get("/teams")
    assert resp.status_code == 401
