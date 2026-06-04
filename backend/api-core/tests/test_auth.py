"""TDD: OAuth 콜백 — user upsert + JWT 발급, 토큰 거부, logout 무효화."""

from __future__ import annotations

from datetime import timedelta

import pytest
import respx
from httpx import Response

from shared.auth import create_access_token, decode_token

from .helpers import make_token, make_user


@pytest.mark.asyncio
async def test_oauth_callback_upserts_user_and_issues_jwt(client, db_session):
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

    payload = decode_token(data["access_token"])
    assert payload["type"] == "access"
    assert payload["login"] == "octocat"


@pytest.mark.asyncio
async def test_oauth_callback_upserts_same_user_twice(client, db_session):
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


@pytest.mark.asyncio
async def test_me_returns_user_info(client, db_session):
    user = await make_user(db_session, login="me_user")
    token, _ = await make_token(db_session, user)
    resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["login"] == "me_user"
    assert data["id"] == str(user.user_id)
    assert "github_id" not in data


@pytest.mark.asyncio
async def test_me_returns_401_without_token(client):
    resp = await client.get("/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_401_with_expired_token(client, db_session):
    user = await make_user(db_session, login="expired")
    token = create_access_token(subject=user.user_id, expires_delta=timedelta(seconds=-1))
    resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_session(client, db_session):
    user = await make_user(db_session, login="logout_user")
    token, _ = await make_token(db_session, user)

    resp = await client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200

    resp2 = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp2.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_without_token_returns_401(client):
    resp = await client.get("/teams")
    assert resp.status_code == 401
