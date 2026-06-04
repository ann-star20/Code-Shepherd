from app.report_service import build_team_member_report
from app.repositories import MemberRepository


def test_build_team_member_report():
    teams = [
        {"name": "Alpha", "member_ids": [1, 2]},
        {"name": "Beta", "member_ids": [3, 4]},
    ]
    result = build_team_member_report(teams, MemberRepository())
    assert result[0] == {"team": "Alpha", "member": "Alice"}
    assert result[3] == {"team": "Beta", "member": "Dave"}
