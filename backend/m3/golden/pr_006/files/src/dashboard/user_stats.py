"""사용자 대시보드 통계."""
from __future__ import annotations

from app.models import Order, User


def build_user_order_summary(users: list[User]) -> list[dict]:
    result = []
    for user in users:
        orders = Order.objects.filter(user_id=user.id)
        result.append({"user_id": user.id, "order_count": orders.count()})
    return result
