from app.order_service import get_orders_with_customers
from app.repositories import CustomerRepository


def test_get_orders_with_customers_bulk():
    orders = [
        {"id": 1, "amount": 100, "customer_id": 1},
        {"id": 2, "amount": 200, "customer_id": 2},
    ]
    result = get_orders_with_customers(orders, CustomerRepository())
    assert result[0]["customer"] == "Alice"
    assert result[1]["customer"] == "Bob"
