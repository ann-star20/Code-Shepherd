"""TDD: 팀 초대 — github_id, 수락/거절, 멤버 프로필 enrichment."""

from __future__ import annotations

import pytest

from .helpers import make_token, make_user
from .invite_helpers import invite_and_accept


async def _create_team_with_lead(client, db_session, lead_login: str):
    lead = await make_user(db_session, login=lead_login)
    token, _ = await make_token(db_session, lead)
    slug = lead_login.replace("_", "-")
    resp = await client.post(
        "/teams",
        json={
            "name": f"{lead_login}'s Team",
            "github_repo": f"org-{slug}/repo-{slug}",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    return resp.json()["id"], token, lead


@pytest.mark.asyncio
async def test_members_list_includes_profile_fields(client, db_session):
    team_id, lead_token, lead = await _create_team_with_lead(client, db_session, "prof_lead")
    lead.github_url = "https://avatars.example/lead.png"
    await db_session.commit()

    resp = await client.get(
        f"/teams/{team_id}/members", headers={"Authorization": f"Bearer {lead_token}"}
    )
    assert resp.status_code == 200
    member = resp.json()[0]
    assert member["login"] == lead.github_id
    assert member["name"] == lead.name
    assert member["avatar_url"] == "https://avatars.example/lead.png"


@pytest.mark.asyncio
async def test_invite_does_not_add_member_until_accepted(client, db_session):
    team_id, lead_token, _ = await _create_team_with_lead(client, db_session, "pend_lead")
    invitee = await make_user(db_session, login="pend_member")
    invitee_token, _ = await make_token(db_session, invitee)

    inv = await client.post(
        f"/teams/{team_id}/invitations",
        json={"user_id": str(invitee.user_id)},
        headers={"Authorization": f"Bearer {lead_token}"},
    )
    assert inv.status_code == 201
    assert inv.json()["status"] == "pending"

    members = await client.get(
        f"/teams/{team_id}/members", headers={"Authorization": f"Bearer {lead_token}"}
    )
    assert not any(m["user_id"] == str(invitee.user_id) for m in members.json())

    mine = await client.get(
        "/invitations", headers={"Authorization": f"Bearer {invitee_token}"}
    )
    assert len(mine.json()) == 1
    assert mine.json()[0]["team_name"] == "pend_lead's Team"


@pytest.mark.asyncio
async def test_accept_invitation_joins_team(client, db_session):
    team_id, lead_token, _ = await _create_team_with_lead(client, db_session, "acc_lead")
    invitee = await make_user(db_session, login="acc_member")
    invitee_token, _ = await make_token(db_session, invitee)

    await invite_and_accept(
        client,
        team_id=team_id,
        lead_token=lead_token,
        invitee_user_id=str(invitee.user_id),
        invitee_token=invitee_token,
    )

    members = await client.get(
        f"/teams/{team_id}/members", headers={"Authorization": f"Bearer {lead_token}"}
    )
    row = next(m for m in members.json() if m["user_id"] == str(invitee.user_id))
    assert row["login"] == "acc_member"
    assert row["role"] == "member"


@pytest.mark.asyncio
async def test_decline_invitation_does_not_join(client, db_session):
    team_id, lead_token, _ = await _create_team_with_lead(client, db_session, "dec_lead")
    invitee = await make_user(db_session, login="dec_member")
    invitee_token, _ = await make_token(db_session, invitee)

    inv = await client.post(
        f"/teams/{team_id}/invitations",
        json={"github_id": "dec_member"},
        headers={"Authorization": f"Bearer {lead_token}"},
    )
    assert inv.status_code == 201
    inv_id = inv.json()["id"]

    dec = await client.post(
        f"/invitations/{inv_id}/decline",
        headers={"Authorization": f"Bearer {invitee_token}"},
    )
    assert dec.status_code == 200
    assert dec.json()["status"] == "declined"

    members = await client.get(
        f"/teams/{team_id}/members", headers={"Authorization": f"Bearer {lead_token}"}
    )
    assert not any(m["user_id"] == str(invitee.user_id) for m in members.json())


@pytest.mark.asyncio
async def test_invite_by_unknown_github_id_returns_404(client, db_session):
    team_id, lead_token, _ = await _create_team_with_lead(client, db_session, "unk_lead")

    resp = await client.post(
        f"/teams/{team_id}/invitations",
        json={"github_id": "nobody_here"},
        headers={"Authorization": f"Bearer {lead_token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_non_invitee_cannot_accept(client, db_session):
    team_id, lead_token, _ = await _create_team_with_lead(client, db_session, "forb_lead")
    invitee = await make_user(db_session, login="forb_member")
    outsider = await make_user(db_session, login="forb_out")
    outsider_token, _ = await make_token(db_session, outsider)

    inv = await client.post(
        f"/teams/{team_id}/invitations",
        json={"user_id": str(invitee.user_id)},
        headers={"Authorization": f"Bearer {lead_token}"},
    )
    inv_id = inv.json()["id"]

    resp = await client.post(
        f"/invitations/{inv_id}/accept",
        headers={"Authorization": f"Bearer {outsider_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_duplicate_pending_invite_returns_409(client, db_session):
    team_id, lead_token, _ = await _create_team_with_lead(client, db_session, "dupinv_lead")
    invitee = await make_user(db_session, login="dupinv_member")

    r1 = await client.post(
        f"/teams/{team_id}/invitations",
        json={"user_id": str(invitee.user_id)},
        headers={"Authorization": f"Bearer {lead_token}"},
    )
    r2 = await client.post(
        f"/teams/{team_id}/invitations",
        json={"user_id": str(invitee.user_id)},
        headers={"Authorization": f"Bearer {lead_token}"},
    )
    assert r1.status_code == 201
    assert r2.status_code == 409
