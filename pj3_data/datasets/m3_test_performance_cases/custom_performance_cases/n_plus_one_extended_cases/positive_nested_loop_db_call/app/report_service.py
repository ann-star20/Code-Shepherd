def build_team_member_report(teams, member_repository):
    report = []
    for team in teams:
        for member_id in team["member_ids"]:
            member = member_repository.find_by_id(member_id)
            report.append({
                "team": team["name"],
                "member": member["name"] if member else None,
            })
    return report
