"""TDD: 팀 CRUD, 멤버 관리, 권한 가드 — lead/member 정책 검증."""

from __future__ import annotations

import pytest

from shared.auth import create_access_token


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

async def _make_user(db_session, user_id: int, login: str):
    from app.models.user import User

    u = User(id=user_id, github_id=user_id * 100, login=login, name=login.capitalize())
    db_session.add(u)
    await db_session.flush()
    return u


async def _make_token(db_session, user_id: int):
    from app.models.session import UserSession
    from datetime import datetime, UTC, timedelta
    import uuid

    jti = str(uuid.uuid4())
    token = create_access_token(subject=user_id, extra_claims={"jti": jti})
    sess = UserSession(
        user_id=user_id,
        token_jti=jti,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(sess)
    await db_session.commit()
    return token, jti


async def _create_team_with_lead(client, db_session, lead_id: int, lead_login: str):
    """팀 생성 후 lead 토큰 반환."""
    await _make_user(db_session, lead_id, lead_login)
    token, _ = await _make_token(db_session, lead_id)
    resp = await client.post(
        "/teams", json={"name": f"{lead_login}'s Team"}, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 201
    return resp.json()["id"], token


# ---------------------------------------------------------------------------
# 팀 생성
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_team_makes_creator_lead(client, db_session):
    team_id, token = await _create_team_with_lead(client, db_session, 20, "creator")

    resp = await client.get(
        f"/teams/{team_id}/members", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    members = resp.json()
    creator_member = next((m for m in members if m["user_id"] == 20), None)
    assert creator_member is not None
    assert creator_member["role"] == "lead"


@pytest.mark.asyncio
async def test_get_teams_returns_only_my_teams(client, db_session):
    """GET /teams — 내가 속한 팀만 반환."""
    team_id, lead_token = await _create_team_with_lead(client, db_session, 30, "myteam_lead")

    # 다른 사용자
    await _make_user(db_session, 31, "other_user")
    other_token, _ = await _make_token(db_session, 31)

    lead_resp = await client.get("/teams", headers={"Authorization": f"Bearer {lead_token}"})
    other_resp = await client.get("/teams", headers={"Authorization": f"Bearer {other_token}"})

    assert any(t["id"] == team_id for t in lead_resp.json())
    assert not any(t["id"] == team_id for t in other_resp.json())


# ---------------------------------------------------------------------------
# 팀 수정/삭제 권한
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_only_lead_can_update_team(client, db_session):
    team_id, lead_token = await _create_team_with_lead(client, db_session, 40, "update_lead")

    # member 추가
    await _make_user(db_session, 41, "update_member")
    member_token, _ = await _make_token(db_session, 41)
    await client.post(
        f"/teams/{team_id}/members",
        json={"user_id": 41},
        headers={"Authorization": f"Bearer {lead_token}"},
    )

    # lead는 수정 가능
    resp = await client.patch(
        f"/teams/{team_id}", json={"name": "Updated"}, headers={"Authorization": f"Bearer {lead_token}"}
    )
    assert resp.status_code == 200

    # member는 403
    resp2 = await client.patch(
        f"/teams/{team_id}", json={"name": "Bad"}, headers={"Authorization": f"Bearer {member_token}"}
    )
    assert resp2.status_code == 403


@pytest.mark.asyncio
async def test_only_lead_can_delete_team(client, db_session):
    team_id, lead_token = await _create_team_with_lead(client, db_session, 50, "del_lead")

    await _make_user(db_session, 51, "del_member")
    member_token, _ = await _make_token(db_session, 51)
    await client.post(
        f"/teams/{team_id}/members",
        json={"user_id": 51},
        headers={"Authorization": f"Bearer {lead_token}"},
    )

    resp = await client.delete(
        f"/teams/{team_id}", headers={"Authorization": f"Bearer {member_token}"}
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 멤버 관리
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_member_prevents_duplicate(client, db_session):
    team_id, lead_token = await _create_team_with_lead(client, db_session, 60, "nodup_lead")
    await _make_user(db_session, 61, "nodup_member")

    resp1 = await client.post(
        f"/teams/{team_id}/members",
        json={"user_id": 61},
        headers={"Authorization": f"Bearer {lead_token}"},
    )
    resp2 = await client.post(
        f"/teams/{team_id}/members",
        json={"user_id": 61},
        headers={"Authorization": f"Bearer {lead_token}"},
    )
    assert resp1.status_code == 201
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_cannot_remove_last_lead(client, db_session):
    team_id, lead_token = await _create_team_with_lead(client, db_session, 70, "last_lead")

    resp = await client.delete(
        f"/teams/{team_id}/members/70",
        headers={"Authorization": f"Bearer {lead_token}"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_member_cannot_add_members(client, db_session):
    team_id, lead_token = await _create_team_with_lead(client, db_session, 80, "add_lead")

    await _make_user(db_session, 81, "add_member")
    member_token, _ = await _make_token(db_session, 81)
    await client.post(
        f"/teams/{team_id}/members",
        json={"user_id": 81},
        headers={"Authorization": f"Bearer {lead_token}"},
    )

    await _make_user(db_session, 82, "new_guy")
    resp = await client.post(
        f"/teams/{team_id}/members",
        json={"user_id": 82},
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_role_change_lead_to_member_blocked_if_last_lead(client, db_session):
    team_id, lead_token = await _create_team_with_lead(client, db_session, 90, "role_lead")

    resp = await client.patch(
        f"/teams/{team_id}/members/90",
        json={"role": "member"},
        headers={"Authorization": f"Bearer {lead_token}"},
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# PR 현황 권한
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_lead_gets_team_scope_prs(client, db_session):
    team_id, lead_token = await _create_team_with_lead(client, db_session, 100, "pr_lead")

    resp = await client.get(
        f"/teams/{team_id}/prs", headers={"Authorization": f"Bearer {lead_token}"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["scope"] == "team"


@pytest.mark.asyncio
async def test_member_gets_self_scope_prs(client, db_session):
    team_id, lead_token = await _create_team_with_lead(client, db_session, 110, "pr_lead2")

    await _make_user(db_session, 111, "pr_member")
    member_token, _ = await _make_token(db_session, 111)
    await client.post(
        f"/teams/{team_id}/members",
        json={"user_id": 111},
        headers={"Authorization": f"Bearer {lead_token}"},
    )

    resp = await client.get(
        f"/teams/{team_id}/prs", headers={"Authorization": f"Bearer {member_token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["scope"] == "self"


@pytest.mark.asyncio
async def test_non_member_cannot_see_prs(client, db_session):
    team_id, _ = await _create_team_with_lead(client, db_session, 120, "prs_lead")

    await _make_user(db_session, 121, "outsider")
    outsider_token, _ = await _make_token(db_session, 121)

    resp = await client.get(
        f"/teams/{team_id}/prs", headers={"Authorization": f"Bearer {outsider_token}"}
    )
    assert resp.status_code == 403
