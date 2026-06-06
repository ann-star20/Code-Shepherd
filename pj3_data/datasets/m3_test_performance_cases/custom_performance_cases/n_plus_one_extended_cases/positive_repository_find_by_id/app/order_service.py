def get_orders_with_customers(orders, customer_repository):
    result = []
    for order in orders:
        customer = customer_repository.find_by_id(order["customer_id"])
        result.append({
            "order_id": order["id"],
            "amount": order["amount"],
            "customer": customer["name"] if customer else None,
        })
    return result
