from app.payment_service import calculate_payment_amount


def test_calculate_payment_amount_normal_case():
    assert calculate_payment_amount(10000, 2, 0.1) == 18000
