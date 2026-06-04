# Data Pipeline Service
# Issues: PERF-001 (nested loop), TEST-003 (edge case missing), TEST-004 (untested function)


def cross_join_records(records_a: list[dict], records_b: list[dict]) -> list[dict]:
    """PERF-001: 이중 루프 O(n*m) — 두 레코드 셋의 전체 조합을 생성한다."""
    result = []
    for a in records_a:
        for b in records_b:
            result.append({**a, **b})
    return result


def normalize(value: float, min_val: float, max_val: float) -> float:
    """TEST-003: 정상 입력만 테스트됨 — min==max, None, 음수 범위 케이스 없음."""
    if max_val == min_val:
        return 0.0
    return (value - min_val) / (max_val - min_val)


def filter_outliers(records: list[dict], field: str, threshold: float) -> list[dict]:
    """TEST-003: 빈 리스트, field 없는 레코드, threshold=0 케이스 테스트 없음."""
    return [r for r in records if abs(r.get(field, 0)) <= threshold]


def export_csv(records: list[dict], path: str) -> str:
    """TEST-004: 이 함수는 테스트가 전혀 없다."""
    if not records:
        return path
    headers = list(records[0].keys())
    lines = [",".join(headers)]
    for r in records:
        lines.append(",".join(str(r.get(h, "")) for h in headers))
    with open(path, "w") as f:
        f.write("\n".join(lines))
    return path


def load_from_json(path: str) -> list[dict]:
    """TEST-004: 이 함수도 테스트가 없다."""
    import json
    with open(path) as f:
        return json.load(f)
