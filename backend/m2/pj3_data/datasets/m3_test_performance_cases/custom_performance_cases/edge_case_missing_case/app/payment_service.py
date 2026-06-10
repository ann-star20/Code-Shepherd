def calculate_payment_amount(price, quantity, discount_rate):
    subtotal = price * quantity
    discount = subtotal * discount_rate
    return subtotal - discount


def validate_payment_amount(amount):
    if amount <= 0:
        raise ValueError("Payment amount must be positive")
    return True
