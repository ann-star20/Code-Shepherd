import pytest
from app.order_service import load_orders_with_items, find_duplicate_orders


def test_load_orders_returns_list():
    result = load_orders_with_items([1, 2])
    assert isinstance(result, list)
    assert len(result) == 2


def test_find_duplicate_orders_no_duplicates():
    orders = [
        {"id": 1, "items": [{"product_id": 1}]},
        {"id": 2, "items": [{"product_id": 2}]},
    ]
    result = find_duplicate_orders(orders)
    assert result == []


# calculate_discount, apply_coupon 는 테스트 없음 → TEST-001 (커버리지 미달)
