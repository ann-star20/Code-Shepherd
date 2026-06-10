# Dashboard Analytics Service
# Issues: PERF-001 (nested loop), PERF-002 (N+1), TEST-004 (untested function), PERF-003 (memory leak)

_event_log: list = []  # PERF-003: 전역 리스트 무제한 누적


class MetricRepository:
    def find_by_user(self, user_id: int) -> dict:
        return {"user_id": user_id, "score": user_id * 10, "views": user_id * 5}


repo = MetricRepository()


def load_metrics(user_ids: list[int]) -> list[dict]:
    """PERF-002: 루프마다 DB 호출."""
    metrics = []
    for user_id in user_ids:
        m = repo.find_by_user(user_id)            # N+1
        _event_log.append({"action": "load", "user_id": user_id})  # PERF-003
        metrics.append(m)
    return metrics


def rank_users(metrics: list[dict]) -> list[dict]:
    """PERF-001: 이중 루프로 각 유저의 상대 순위를 계산한다."""
    ranked = []
    for m in metrics:
        rank = 1
        for other in metrics:           # PERF-001: 중첩 루프 O(n²)
            if other["score"] > m["score"]:
                rank += 1
        ranked.append({**m, "rank": rank})
    return ranked


def export_pdf(data: list[dict], path: str) -> str:
    """TEST-004: 이 함수는 테스트가 전혀 없다."""
    _event_log.append({"action": "export_pdf"})   # PERF-003
    # PDF 생성 로직 (시뮬레이션)
    with open(path, "w") as f:
        f.write(str(data))
    return path


def archive_dashboard(snapshot_id: str, data: list[dict]) -> bool:
    """TEST-004: 이 함수도 테스트가 없다."""
    _event_log.append({"action": "archive", "snapshot_id": snapshot_id})  # PERF-003
    return True
