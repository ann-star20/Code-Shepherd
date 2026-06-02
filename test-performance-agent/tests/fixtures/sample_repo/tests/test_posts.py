from src.posts import calc_discount


def test_calc_discount():
    assert calc_discount(1000, 0.1) == 900
