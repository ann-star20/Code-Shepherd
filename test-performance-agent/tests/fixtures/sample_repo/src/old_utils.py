"""레거시 유틸 - 신입이 이번 PR에서 건드리지 않은 파일.

여기에도 N+1이 있지만, diff에 없으므로 교집합 필터가 걸러내야 한다(③ 검증용).
"""


def load_all(ids):
    out = []
    for i in ids:
        out.append(db.query(f"select * from t where id={i}"))
    return out
