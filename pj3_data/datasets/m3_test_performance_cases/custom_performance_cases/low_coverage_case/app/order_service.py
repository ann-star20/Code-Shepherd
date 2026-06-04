def calculate_total(items):
    total = 0
    for item in items:
        total += item["price"] * item["quantity"]
    return total


def apply_discount(total, coupon_code):
    if coupon_code == "WELCOME":
        return total * 0.9
    if coupon_code == "VIP":
        return total * 0.8
    return total


def calculate_shipping(total, region):
    if region == "jeju":
        return 6000
    if total >= 50000:
        return 0
    return 3000


def create_order_summary(items, coupon_code, region):
    total = calculate_total(items)
    discounted = apply_discount(total, coupon_code)
    shipping = calculate_shipping(discounted, region)
    return {
        "total": total,
        "discounted": discounted,
        "shipping": shipping,
        "pay_amount": discounted + shipping,
    }
