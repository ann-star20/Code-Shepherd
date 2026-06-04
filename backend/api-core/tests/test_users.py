"""TDD: GET /users 검색 — 민감정보 미노출."""

from __future__ import annotations

import pytest

from shared.auth import create_access_token


async def _setup_users(db_session):
    """테스트용 유저 3명 생성."""
    from app.models.user import User
    from app.models.session import UserSession
    from datetime import datetime, UTC, timedelta
    import uuid

    users = [
        User(id=10, github_id=1010, login="alice", name="Alice Smith"),
        User(id=11, github_id=1011, login="bob_dev", name="Bob Jones"),
        User(id=12, github_id=1012, login="charlie", name=None),
    ]
    for u in users:
        db_session.add(u)
    await db_session.flush()

    # 인증용 세션
    jti = str(uuid.uuid4())
    token = create_access_token(subject=10, extra_claims={"jti": jti})
    sess = UserSession(
        user_id=10,
        token_jti=jti,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(sess)
    await db_session.commit()
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
    """응답에 github_id 등 민감정보 없음."""
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
