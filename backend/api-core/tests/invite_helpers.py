"""팀 초대 플로우 테스트 헬퍼."""

from __future__ import annotations


async def invite_and_accept(
    client,
    *,
    team_id: str,
    lead_token: str,
    invitee_user_id: str,
    invitee_token: str,
    github_id: str | None = None,
) -> str:
    body: dict = {"user_id": invitee_user_id}
    if github_id:
        body = {"github_id": github_id}
    resp = await client.post(
        f"/teams/{team_id}/invitations",
        json=body,
        headers={"Authorization": f"Bearer {lead_token}"},
    )
    assert resp.status_code == 201, resp.text
    inv_resp = await client.get(
        "/invitations", headers={"Authorization": f"Bearer {invitee_token}"}
    )
    assert inv_resp.status_code == 200
    invitations = inv_resp.json()
    assert len(invitations) >= 1
    inv_id = invitations[0]["id"]
    acc = await client.post(
        f"/invitations/{inv_id}/accept",
        headers={"Authorization": f"Bearer {invitee_token}"},
    )
    assert acc.status_code == 200, acc.text
    return inv_id
