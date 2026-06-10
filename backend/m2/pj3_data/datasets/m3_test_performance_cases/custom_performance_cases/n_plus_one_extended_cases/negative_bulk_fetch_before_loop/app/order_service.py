def get_orders_with_customers(orders, customer_repository):
    customer_ids = {order["customer_id"] for order in orders}
    customers_by_id = customer_repository.find_all_by_ids(customer_ids)
    result = []
    for order in orders:
        customer = customers_by_id.get(order["customer_id"])
        result.append({
            "order_id": order["id"],
            "amount": order["amount"],
            "customer": customer["name"] if customer else None,
        })
    return result
