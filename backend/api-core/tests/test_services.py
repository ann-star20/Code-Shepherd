"""서비스 레이어 직접 테스트 — 커버리지 보강."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.models.team import Team, TeamMember
from app.models.user import User
from app.services.team_service import (
    _count_leads,
    _require_lead,
    _require_member,
    add_member,
    create_team,
    delete_team,
    get_members,
    get_team_or_404,
    get_teams_for_user,
    remove_member,
    search_users,
    update_member_role,
    update_team,
)


async def _add_user(db, user_id: int, login: str) -> User:
    u = User(id=user_id, github_id=user_id * 1000, login=login, name=login.title())
    db.add(u)
    await db.flush()
    return u


async def _add_team_with_lead(db, lead_id: int, name: str = "Test Team") -> Team:
    return await create_team(db, name, lead_id)


# ---------------------------------------------------------------------------
# get_teams_for_user
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_teams_for_user_returns_user_teams(db_session):
    await _add_user(db_session, 1, "alice")
    team = await _add_team_with_lead(db_session, 1)
    teams = await get_teams_for_user(db_session, 1)
    assert any(t.id == team.id for t in teams)


@pytest.mark.asyncio
async def test_get_teams_for_user_excludes_others(db_session):
    await _add_user(db_session, 2, "bob")
    await _add_user(db_session, 3, "charlie")
    team = await _add_team_with_lead(db_session, 2)
    teams = await get_teams_for_user(db_session, 3)
    assert not any(t.id == team.id for t in teams)


# ---------------------------------------------------------------------------
# get_team_or_404
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_team_or_404_found(db_session):
    await _add_user(db_session, 4, "dave")
    team = await _add_team_with_lead(db_session, 4)
    found = await get_team_or_404(db_session, team.id)
    assert found.id == team.id


@pytest.mark.asyncio
async def test_get_team_or_404_not_found(db_session):
    with pytest.raises(HTTPException) as exc:
        await get_team_or_404(db_session, 9999)
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# create_team
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_team_creator_becomes_lead(db_session):
    await _add_user(db_session, 5, "emma")
    team = await create_team(db_session, "Emma's Team", 5)
    members = await get_members(db_session, team.id, 5)
    lead = next(m for m in members if m.user_id == 5)
    assert lead.role == "lead"


# ---------------------------------------------------------------------------
# update_team
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_team_by_lead(db_session):
    await _add_user(db_session, 6, "frank")
    team = await create_team(db_session, "Old Name", 6)
    updated = await update_team(db_session, team.id, 6, "New Name")
    assert updated.name == "New Name"


@pytest.mark.asyncio
async def test_update_team_by_non_lead_raises(db_session):
    await _add_user(db_session, 7, "grace")
    await _add_user(db_session, 8, "henry")
    team = await create_team(db_session, "Grace's Team", 7)
    await add_member(db_session, team.id, 7, 8)
    with pytest.raises(HTTPException) as exc:
        await update_team(db_session, team.id, 8, "Bad Update")
    assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# delete_team
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_team_soft_deletes(db_session):
    await _add_user(db_session, 9, "iris")
    team = await create_team(db_session, "Iris Team", 9)
    await delete_team(db_session, team.id, 9)
    with pytest.raises(HTTPException):
        await get_team_or_404(db_session, team.id)


# ---------------------------------------------------------------------------
# add_member / remove_member
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_member_success(db_session):
    await _add_user(db_session, 10, "jack")
    await _add_user(db_session, 11, "kate")
    team = await create_team(db_session, "JK Team", 10)
    member = await add_member(db_session, team.id, 10, 11)
    assert member.role == "member"


@pytest.mark.asyncio
async def test_remove_member_success(db_session):
    await _add_user(db_session, 12, "liam")
    await _add_user(db_session, 13, "mia")
    team = await create_team(db_session, "LM Team", 12)
    await add_member(db_session, team.id, 12, 13)
    await remove_member(db_session, team.id, 12, 13)
    members = await get_members(db_session, team.id, 12)
    assert not any(m.user_id == 13 for m in members)


@pytest.mark.asyncio
async def test_remove_nonexistent_member_raises(db_session):
    await _add_user(db_session, 14, "noah")
    team = await create_team(db_session, "Noah Team", 14)
    with pytest.raises(HTTPException) as exc:
        await remove_member(db_session, team.id, 14, 9999)
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# update_member_role
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_role_member_to_lead(db_session):
    await _add_user(db_session, 15, "olivia")
    await _add_user(db_session, 16, "paul")
    team = await create_team(db_session, "OP Team", 15)
    await add_member(db_session, team.id, 15, 16)
    updated = await update_member_role(db_session, team.id, 15, 16, "lead")
    assert updated.role == "lead"


@pytest.mark.asyncio
async def test_update_role_nonexistent_member_raises(db_session):
    await _add_user(db_session, 17, "quinn")
    team = await create_team(db_session, "Q Team", 17)
    with pytest.raises(HTTPException) as exc:
        await update_member_role(db_session, team.id, 17, 9999, "lead")
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# search_users
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_users_by_login(db_session):
    await _add_user(db_session, 18, "rachel")
    await _add_user(db_session, 19, "samantha")
    results = await search_users(db_session, "rachel")
    assert any(u.login == "rachel" for u in results)
    assert not any(u.login == "samantha" for u in results)


@pytest.mark.asyncio
async def test_search_users_empty_query_returns_all(db_session):
    await _add_user(db_session, 20, "tim")
    results = await search_users(db_session, "")
    assert len(results) >= 1


# ---------------------------------------------------------------------------
# _require_member / _require_lead
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_require_member_raises_for_non_member(db_session):
    await _add_user(db_session, 21, "uma")
    await _add_user(db_session, 22, "victor")
    team = await create_team(db_session, "UV Team", 21)
    with pytest.raises(HTTPException) as exc:
        await _require_member(db_session, team.id, 22)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_lead_raises_for_member(db_session):
    await _add_user(db_session, 23, "wendy")
    await _add_user(db_session, 24, "xavier")
    team = await create_team(db_session, "WX Team", 23)
    await add_member(db_session, team.id, 23, 24)
    with pytest.raises(HTTPException) as exc:
        await _require_lead(db_session, team.id, 24)
    assert exc.value.status_code == 403
