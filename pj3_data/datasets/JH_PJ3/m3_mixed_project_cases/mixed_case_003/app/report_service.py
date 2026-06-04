# Report Service
# Issues: PERF-002 (N+1 query), TEST-001 (low coverage), PERF-003 (memory leak)

_report_cache: dict = {}  # PERF-003: 전역 dict에 무제한 누적


class DeptRepository:
    def find_by_id(self, dept_id: int) -> dict:
        return {"id": dept_id, "name": f"dept_{dept_id}"}

    def find_members(self, dept_id: int) -> list:
        return [{"user_id": i} for i in range(1, 4)]


repo = DeptRepository()


def generate_report(dept_ids: list[int]) -> list[dict]:
    """PERF-002: for 루프 안에서 DB 호출 두 번 반복."""
    reports = []
    for dept_id in dept_ids:
        dept = repo.find_by_id(dept_id)          # N+1
        members = repo.find_members(dept_id)      # N+1
        report = {"dept": dept, "member_count": len(members)}
        _report_cache[dept_id] = report           # PERF-003: 캐시에 계속 누적
        reports.append(report)
    return reports


def summarize(reports: list[dict]) -> dict:
    """TEST-001: 이 함수는 테스트가 없다."""
    total = sum(r["member_count"] for r in reports)
    return {"total_members": total, "dept_count": len(reports)}


def export_csv(reports: list[dict], path: str) -> str:
    """TEST-001: 이 함수도 테스트가 없다."""
    lines = ["dept_id,member_count"]
    for r in reports:
        lines.append(f"{r['dept']['id']},{r['member_count']}")
    with open(path, "w") as f:
        f.write("\n".join(lines))
    return path
