"""TDD: 팀 CRUD, 멤버 관리, 권한 가드 — users.team 기반."""

from __future__ import annotations

import pytest

from .helpers import make_token, make_user
from .invite_helpers import invite_and_accept


async def _create_team_with_lead(
    client,
    db_session,
    lead_login: str,
    *,
    repo_slug: str | None = None,
):
    lead = await make_user(db_session, login=lead_login)
    token, _ = await make_token(db_session, lead)
    slug = repo_slug or lead_login.replace("_", "-")
    resp = await client.post(
        "/teams",
        json={
            "name": f"{lead_login}'s Team",
            "github_repo": f"org-{slug}/repo-{slug}",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "github_repo" in data
    return data["id"], token, lead


@pytest.mark.asyncio
async def test_create_team_makes_creator_lead(client, db_session):
    team_id, token, lead = await _create_team_with_lead(client, db_session, "creator")

    resp = await client.get(
        f"/teams/{team_id}/members", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    members = resp.json()
    creator_member = next((m for m in members if m["user_id"] == str(lead.user_id)), None)
    assert creator_member is not None
    assert creator_member["role"] == "lead"


@pytest.mark.asyncio
async def test_get_teams_returns_only_my_teams(client, db_session):
    team_id, lead_token, _ = await _create_team_with_lead(client, db_session, "myteam_lead")

    other = await make_user(db_session, login="other_user")
    other_token, _ = await make_token(db_session, other)

    lead_resp = await client.get("/teams", headers={"Authorization": f"Bearer {lead_token}"})
    other_resp = await client.get("/teams", headers={"Authorization": f"Bearer {other_token}"})

    assert any(t["id"] == team_id for t in lead_resp.json())
    assert not any(t["id"] == team_id for t in other_resp.json())


@pytest.mark.asyncio
async def test_only_lead_can_update_team(client, db_session):
    team_id, lead_token, lead = await _create_team_with_lead(client, db_session, "update_lead")

    member = await make_user(db_session, login="update_member")
    member_token, _ = await make_token(db_session, member)
    await invite_and_accept(
        client,
        team_id=team_id,
        lead_token=lead_token,
        invitee_user_id=str(member.user_id),
        invitee_token=member_token,
    )

    resp = await client.patch(
        f"/teams/{team_id}", json={"name": "Updated"}, headers={"Authorization": f"Bearer {lead_token}"}
    )
    assert resp.status_code == 200
    renamed_team_id = resp.json()["id"]

    resp2 = await client.patch(
        f"/teams/{renamed_team_id}",
        json={"name": "Bad"},
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert resp2.status_code == 403


@pytest.mark.asyncio
async def test_only_lead_can_delete_team(client, db_session):
    team_id, lead_token, _ = await _create_team_with_lead(client, db_session, "del_lead")

    member = await make_user(db_session, login="del_member")
    member_token, _ = await make_token(db_session, member)
    await invite_and_accept(
        client,
        team_id=team_id,
        lead_token=lead_token,
        invitee_user_id=str(member.user_id),
        invitee_token=member_token,
    )

    resp = await client.delete(
        f"/teams/{team_id}", headers={"Authorization": f"Bearer {member_token}"}
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_invite_prevents_duplicate_pending(client, db_session):
    team_id, lead_token, _ = await _create_team_with_lead(client, db_session, "nodup_lead")
    member = await make_user(db_session, login="nodup_member")

    resp1 = await client.post(
        f"/teams/{team_id}/invitations",
        json={"user_id": str(member.user_id)},
        headers={"Authorization": f"Bearer {lead_token}"},
    )
    resp2 = await client.post(
        f"/teams/{team_id}/invitations",
        json={"user_id": str(member.user_id)},
        headers={"Authorization": f"Bearer {lead_token}"},
    )
    assert resp1.status_code == 201
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_cannot_remove_last_lead(client, db_session):
    team_id, lead_token, lead = await _create_team_with_lead(client, db_session, "last_lead")

    resp = await client.delete(
        f"/teams/{team_id}/members/{lead.user_id}",
        headers={"Authorization": f"Bearer {lead_token}"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_member_cannot_add_members(client, db_session):
    team_id, lead_token, _ = await _create_team_with_lead(client, db_session, "add_lead")

    member = await make_user(db_session, login="add_member")
    member_token, _ = await make_token(db_session, member)
    await invite_and_accept(
        client,
        team_id=team_id,
        lead_token=lead_token,
        invitee_user_id=str(member.user_id),
        invitee_token=member_token,
    )

    new_guy = await make_user(db_session, login="new_guy")
    resp = await client.post(
        f"/teams/{team_id}/members",
        json={"user_id": str(new_guy.user_id)},
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_role_change_lead_to_member_blocked_if_last_lead(client, db_session):
    team_id, lead_token, lead = await _create_team_with_lead(client, db_session, "role_lead")

    resp = await client.patch(
        f"/teams/{team_id}/members/{lead.user_id}",
        json={"role": "member"},
        headers={"Authorization": f"Bearer {lead_token}"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_lead_gets_team_scope_prs(client, db_session):
    team_id, lead_token, _ = await _create_team_with_lead(client, db_session, "pr_lead")

    resp = await client.get(
        f"/teams/{team_id}/prs", headers={"Authorization": f"Bearer {lead_token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["scope"] == "team"


@pytest.mark.asyncio
async def test_member_gets_self_scope_prs(client, db_session):
    team_id, lead_token, _ = await _create_team_with_lead(client, db_session, "pr_lead2")

    member = await make_user(db_session, login="pr_member")
    member_token, _ = await make_token(db_session, member)
    await invite_and_accept(
        client,
        team_id=team_id,
        lead_token=lead_token,
        invitee_user_id=str(member.user_id),
        invitee_token=member_token,
    )

    resp = await client.get(
        f"/teams/{team_id}/prs", headers={"Authorization": f"Bearer {member_token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["scope"] == "self"


@pytest.mark.asyncio
async def test_create_team_requires_valid_github_repo(client, db_session):
    lead = await make_user(db_session, login="repo_fmt")
    token, _ = await make_token(db_session, lead)

    resp = await client.post(
        "/teams",
        json={"name": "Bad Repo Team", "github_repo": "not-valid"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_duplicate_github_repo_rejected(client, db_session):
    _, token1, _ = await _create_team_with_lead(
        client, db_session, "repo_a", repo_slug="shared"
    )

    lead2 = await make_user(db_session, login="repo_b")
    token2, _ = await make_token(db_session, lead2)
    resp = await client.post(
        "/teams",
        json={"name": "Other Team", "github_repo": "org-shared/repo-shared"},
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_lead_can_update_github_repo(client, db_session):
    team_id, token, _ = await _create_team_with_lead(client, db_session, "upd_repo")

    resp = await client.patch(
        f"/teams/{team_id}",
        json={"github_repo": "org-upd-repo/new-repo"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["github_repo"] == "org-upd-repo/new-repo"


@pytest.mark.asyncio
async def test_non_member_cannot_see_prs(client, db_session):
    team_id, _, _ = await _create_team_with_lead(client, db_session, "prs_lead")

    outsider = await make_user(db_session, login="outsider")
    outsider_token, _ = await make_token(db_session, outsider)

    resp = await client.get(
        f"/teams/{team_id}/prs", headers={"Authorization": f"Bearer {outsider_token}"}
    )
    assert resp.status_code == 403
