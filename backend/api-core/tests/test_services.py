"""서비스 레이어 직접 테스트 — teams / team_members."""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from app.services.team_service import (
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

from .helpers import make_user

DEFAULT_REPO = "test-org/test-repo"


@pytest.mark.asyncio
async def test_get_teams_for_user_returns_user_teams(db_session):
    lead = await make_user(db_session, login="alice")
    team = await create_team(db_session, "Alice Team", DEFAULT_REPO, lead.user_id)
    teams = await get_teams_for_user(db_session, lead.user_id)
    assert any(t.id == team.id for t in teams)


@pytest.mark.asyncio
async def test_get_teams_for_user_excludes_others(db_session):
    lead = await make_user(db_session, login="bob")
    other = await make_user(db_session, login="charlie")
    team = await create_team(db_session, "Bob Team", "bob-org/bob-repo", lead.user_id)
    teams = await get_teams_for_user(db_session, other.user_id)
    assert not any(t.id == team.id for t in teams)


@pytest.mark.asyncio
async def test_get_team_or_404_found(db_session):
    lead = await make_user(db_session, login="dave")
    team = await create_team(db_session, "Dave Team", "dave-org/dave-repo", lead.user_id)
    found = await get_team_or_404(db_session, team.id)
    assert found.name == team.name
    assert found.github_repo_full_name == "dave-org/dave-repo"


@pytest.mark.asyncio
async def test_get_team_or_404_not_found(db_session):
    with pytest.raises(HTTPException) as exc:
        await get_team_or_404(db_session, uuid.uuid4())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_create_team_creator_becomes_lead(db_session):
    lead = await make_user(db_session, login="emma")
    team = await create_team(db_session, "Emma's Team", "emma-org/emma-repo", lead.user_id)
    members = await get_members(db_session, team.id, lead.user_id)
    creator = next(m for m in members if m.user_id == lead.user_id)
    assert creator.role == "lead"


@pytest.mark.asyncio
async def test_update_team_by_lead(db_session):
    lead = await make_user(db_session, login="frank")
    team = await create_team(db_session, "Old Name", "frank-org/old-repo", lead.user_id)
    updated = await update_team(
        db_session, team.id, lead.user_id, new_name="New Name"
    )
    assert updated.name == "New Name"
    assert updated.id == team.id


@pytest.mark.asyncio
async def test_update_team_by_non_lead_raises(db_session):
    lead = await make_user(db_session, login="grace")
    member = await make_user(db_session, login="henry")
    team = await create_team(db_session, "Grace's Team", "grace-org/grace-repo", lead.user_id)
    await add_member(db_session, team.id, lead.user_id, member.user_id)
    with pytest.raises(HTTPException) as exc:
        await update_team(
            db_session, team.id, member.user_id, new_name="Bad Update"
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_delete_team_clears_members(db_session):
    lead = await make_user(db_session, login="iris")
    team = await create_team(db_session, "Iris Team", "iris-org/iris-repo", lead.user_id)
    await delete_team(db_session, team.id, lead.user_id)
    with pytest.raises(HTTPException):
        await get_team_or_404(db_session, team.id)


@pytest.mark.asyncio
async def test_add_member_success(db_session):
    lead = await make_user(db_session, login="jack")
    member = await make_user(db_session, login="kate")
    team = await create_team(db_session, "JK Team", "jk-org/jk-repo", lead.user_id)
    added = await add_member(db_session, team.id, lead.user_id, member.user_id)
    assert added.role == "member"


@pytest.mark.asyncio
async def test_remove_member_success(db_session):
    lead = await make_user(db_session, login="liam")
    member = await make_user(db_session, login="mia")
    team = await create_team(db_session, "LM Team", "lm-org/lm-repo", lead.user_id)
    await add_member(db_session, team.id, lead.user_id, member.user_id)
    await remove_member(db_session, team.id, lead.user_id, member.user_id)
    members = await get_members(db_session, team.id, lead.user_id)
    assert not any(m.user_id == member.user_id for m in members)


@pytest.mark.asyncio
async def test_remove_nonexistent_member_raises(db_session):
    lead = await make_user(db_session, login="noah")
    team = await create_team(db_session, "Noah Team", "noah-org/noah-repo", lead.user_id)
    with pytest.raises(HTTPException) as exc:
        await remove_member(db_session, team.id, lead.user_id, uuid.uuid4())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_update_role_member_to_lead(db_session):
    lead = await make_user(db_session, login="olivia")
    member = await make_user(db_session, login="paul")
    team = await create_team(db_session, "OP Team", "op-org/op-repo", lead.user_id)
    await add_member(db_session, team.id, lead.user_id, member.user_id)
    updated = await update_member_role(
        db_session, team.id, lead.user_id, member.user_id, "lead"
    )
    assert updated.role == "lead"


@pytest.mark.asyncio
async def test_update_role_nonexistent_member_raises(db_session):
    lead = await make_user(db_session, login="quinn")
    team = await create_team(db_session, "Q Team", "q-org/q-repo", lead.user_id)
    with pytest.raises(HTTPException) as exc:
        await update_member_role(db_session, team.id, lead.user_id, uuid.uuid4(), "lead")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_search_users_by_login(db_session):
    await make_user(db_session, login="rachel")
    await make_user(db_session, login="samantha")
    results = await search_users(db_session, "rachel")
    assert any(u.login == "rachel" for u in results)
    assert not any(u.login == "samantha" for u in results)


@pytest.mark.asyncio
async def test_search_users_empty_query_returns_all(db_session):
    await make_user(db_session, login="tim")
    results = await search_users(db_session, "")
    assert len(results) >= 1


@pytest.mark.asyncio
async def test_require_member_raises_for_non_member(db_session):
    lead = await make_user(db_session, login="uma")
    outsider = await make_user(db_session, login="victor")
    team = await create_team(db_session, "UV Team", "uv-org/uv-repo", lead.user_id)
    with pytest.raises(HTTPException) as exc:
        await _require_member(db_session, team.id, outsider.user_id)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_lead_raises_for_member(db_session):
    lead = await make_user(db_session, login="wendy")
    member = await make_user(db_session, login="xavier")
    team = await create_team(db_session, "WX Team", "wx-org/wx-repo", lead.user_id)
    await add_member(db_session, team.id, lead.user_id, member.user_id)
    with pytest.raises(HTTPException) as exc:
        await _require_lead(db_session, team.id, member.user_id)
    assert exc.value.status_code == 403
