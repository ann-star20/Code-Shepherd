"""TDD: GET /users 검색 — 민감정보 미노출."""

from __future__ import annotations

import pytest

from .helpers import make_token, make_user


async def _setup_users(db_session):
    alice = await make_user(db_session, login="alice")
    bob = await make_user(db_session, login="bob_dev")
    bob.name = "Bob Jones"
    await make_user(db_session, login="charlie")
    await db_session.commit()
    token, _ = await make_token(db_session, alice)
    return token


@pytest.mark.asyncio
async def test_search_users_returns_matching(client, db_session):
    token = await _setup_users(db_session)
    resp = await client.get("/users?search=alice", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert any(u["login"] == "alice" for u in data)


@pytest.mark.asyncio
async def test_search_users_no_sensitive_fields(client, db_session):
    token = await _setup_users(db_session)
    resp = await client.get("/users?search=", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    for user in resp.json():
        assert "github_id" not in user
        assert "id" in user
        assert "login" in user
        assert "name" in user
        assert "avatar_url" in user


@pytest.mark.asyncio
async def test_search_users_requires_auth(client):
    resp = await client.get("/users?search=alice")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_search_by_name_partial_match(client, db_session):
    token = await _setup_users(db_session)
    resp = await client.get("/users?search=Jones", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert any(u["login"] == "bob_dev" for u in data)
