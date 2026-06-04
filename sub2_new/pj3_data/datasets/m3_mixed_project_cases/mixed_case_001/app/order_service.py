# Order Service
# Issues: PERF-001 (nested loop), PERF-002 (N+1 query), TEST-001 (low coverage)

class OrderRepository:
    def find_by_id(self, order_id: int) -> dict:
        # Simulated DB call
        return {"id": order_id, "items": [], "total": 0}

    def find_items_by_order(self, order_id: int) -> list:
        # Simulated DB call
        return [{"product_id": 1, "qty": 2}]


repo = OrderRepository()


def load_orders_with_items(order_ids: list[int]) -> list[dict]:
    """PERF-002: N+1 — DB 호출이 루프 안에서 반복된다."""
    orders = []
    for order_id in order_ids:
        order = repo.find_by_id(order_id)          # N+1: 루프마다 DB 호출
        order["items"] = repo.find_items_by_order(order_id)  # N+1: 또 DB 호출
        orders.append(order)
    return orders


def find_duplicate_orders(orders: list[dict]) -> list[tuple]:
    """PERF-001: 중첩 루프 O(n²) — 동일 상품 구성의 주문 쌍을 찾는다."""
    duplicates = []
    for i in range(len(orders)):
        for j in range(i + 1, len(orders)):
            if orders[i].get("items") == orders[j].get("items"):
                duplicates.append((orders[i]["id"], orders[j]["id"]))
    return duplicates


def calculate_discount(price: float, rate: float) -> float:
    """TEST-001: 이 함수는 테스트가 없어 커버리지 미달을 유발한다."""
    if rate < 0 or rate > 1:
        raise ValueError("rate must be between 0 and 1")
    return round(price * (1 - rate), 2)


def apply_coupon(price: float, coupon_code: str) -> float:
    """TEST-001: 이 함수도 테스트가 없다."""
    coupons = {"SAVE10": 0.1, "SAVE20": 0.2}
    rate = coupons.get(coupon_code, 0)
    return calculate_discount(price, rate)
