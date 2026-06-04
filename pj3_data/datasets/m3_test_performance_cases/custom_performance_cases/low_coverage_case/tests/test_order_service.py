from app.order_service import calculate_total


def test_calculate_total():
    items = [
        {"price": 10000, "quantity": 2},
        {"price": 5000, "quantity": 1},
    ]
    assert calculate_total(items) == 25000
