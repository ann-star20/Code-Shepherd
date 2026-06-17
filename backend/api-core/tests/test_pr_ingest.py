"""TDD: PR webhook ingest + 팀별 PR 목록."""

from __future__ import annotations

import pytest

from app.services.pr_service import ingest_pr_from_webhook, list_prs_for_team
from app.services.team_service import add_member, create_team

from .helpers import make_token, make_user

INTERNAL_HEADERS = {"X-Internal-Token": "dev-internal-token"}


async def _team_with_repo(db_session, lead_login: str, repo: str):
    lead = await make_user(db_session, login=lead_login, github_id=lead_login)
    team = await create_team(db_session, f"{lead_login} team", repo, lead.user_id)
    return team, lead


@pytest.mark.asyncio
async def test_internal_pr_ingest_creates_pull_request(client, db_session):
    repo = "acme-org/acme-repo"
    team, lead = await _team_with_repo(db_session, "ingest_lead", repo)

    resp = await client.post(
        "/internal/pr-ingest",
        json={
            "repository_full_name": repo,
            "sender_github_login": "ingest_lead",
            "pr_number": 7,
            "pr_url": "https://github.com/acme-org/acme-repo/pull/7",
            "action": "opened",
            "pull_request": {},
        },
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["created"] is True
    assert data["team_id"] == str(team.id)

    token, _ = await make_token(db_session, lead)
    prs_resp = await client.get(
        f"/teams/{team.id}/prs",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert prs_resp.status_code == 200
    prs = prs_resp.json()["prs"]
    assert len(prs) == 1
    assert prs[0]["github_pr_number"] == 7
    assert prs[0]["author_login"] == "ingest_lead"


@pytest.mark.asyncio
async def test_internal_pr_ingest_requires_token(client, db_session):
    await _team_with_repo(db_session, "tok_lead", "tok-org/tok-repo")
    resp = await client.post(
        "/internal/pr-ingest",
        json={
            "repository_full_name": "tok-org/tok-repo",
            "sender_github_login": "tok_lead",
            "pr_number": 1,
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_ingest_unknown_repo_returns_404(client, db_session):
    resp = await client.post(
        "/internal/pr-ingest",
        json={
            "repository_full_name": "unknown/org-repo",
            "sender_github_login": "nobody",
            "pr_number": 1,
        },
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_lead_sees_member_pr(client, db_session):
    repo = "shared-org/shared-repo"
    team, lead = await _team_with_repo(db_session, "lead_pr", repo)
    member = await make_user(db_session, login="member_pr", github_id="member_pr")
    await add_member(db_session, team.id, lead.user_id, member.user_id)

    await ingest_pr_from_webhook(
        db_session,
        repository_full_name=repo,
        sender_github_login="member_pr",
        pr_number=99,
        pr_url="https://github.com/shared-org/shared-repo/pull/99",
        action="opened",
    )

    scope, prs = await list_prs_for_team(db_session, team.id, lead.user_id)
    assert scope == "team"
    assert len(prs) == 1
    assert prs[0].github_pr_number == 99


@pytest.mark.asyncio
async def test_member_sees_only_own_pr(client, db_session):
    repo = "scope-org/scope-repo"
    team, lead = await _team_with_repo(db_session, "scope_lead", repo)
    member = await make_user(db_session, login="scope_member", github_id="scope_member")
    await add_member(db_session, team.id, lead.user_id, member.user_id)

    await ingest_pr_from_webhook(
        db_session,
        repository_full_name=repo,
        sender_github_login="scope_lead",
        pr_number=1,
        pr_url=None,
        action="opened",
    )
    await ingest_pr_from_webhook(
        db_session,
        repository_full_name=repo,
        sender_github_login="scope_member",
        pr_number=2,
        pr_url=None,
        action="opened",
    )

    scope, prs = await list_prs_for_team(db_session, team.id, member.user_id)
    assert scope == "self"
    assert len(prs) == 1
    assert prs[0].github_pr_number == 2


@pytest.mark.asyncio
async def test_ingest_updates_existing_pr_status(db_session):
    repo = "upd-org/upd-repo"
    team, lead = await _team_with_repo(db_session, "upd_lead", repo)

    await ingest_pr_from_webhook(
        db_session,
        repository_full_name=repo,
        sender_github_login="upd_lead",
        pr_number=5,
        pr_url=None,
        action="opened",
        pull_request={},
    )
    await ingest_pr_from_webhook(
        db_session,
        repository_full_name=repo,
        sender_github_login="upd_lead",
        pr_number=5,
        pr_url=None,
        action="closed",
        pull_request={"merged": True},
    )

    _, prs = await list_prs_for_team(db_session, team.id, lead.user_id)
    assert len(prs) == 1
    assert prs[0].status == "merged"
