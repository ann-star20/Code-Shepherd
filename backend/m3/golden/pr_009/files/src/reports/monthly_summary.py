"""월별 리포트."""
from __future__ import annotations

from common import repo


def build_monthly_summary(user_ids: list[int]) -> list[dict]:
    orders = repo.bulk_fetch("orders", ids=user_ids)
    return [
        {"user_id": uid, "order_count": len(orders.get(uid, []))}
        for uid in user_ids
    ]
