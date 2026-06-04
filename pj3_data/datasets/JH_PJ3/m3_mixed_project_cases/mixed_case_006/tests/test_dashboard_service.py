import pytest
from app.dashboard_service import load_metrics, rank_users


def test_load_metrics_returns_list():
    result = load_metrics([1, 2, 3])
    assert len(result) == 3


def test_rank_users_basic():
    metrics = [
        {"user_id": 1, "score": 30, "views": 5},
        {"user_id": 2, "score": 50, "views": 10},
        {"user_id": 3, "score": 20, "views": 3},
    ]
    result = rank_users(metrics)
    scores = {r["user_id"]: r["rank"] for r in result}
    assert scores[2] == 1  # 최고 점수 → 1등

# export_pdf, archive_dashboard 테스트 없음 → TEST-004
