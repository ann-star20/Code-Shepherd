"""양성 라벨 케이스 — N+1(PERF-002) + 3중 중첩루프(PERF-001).

인자명(user_ids·items)이 휴리스틱 엣지케이스 키워드를 포함 → TEST-003 도 함께 발생.
"""


def get_users(user_ids):
    rows = []
    for uid in user_ids:
        row = db.query("SELECT * FROM users WHERE id=" + str(uid))
        rows.append(row)
    return rows


def find_triples(items):
    out = []
    for a in items:
        for b in items:
            for c in items:
                out.append((a, b, c))
    return out
