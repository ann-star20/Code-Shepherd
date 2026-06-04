from app.user_metrics import average_score


def test_average_score():
    assert average_score([80, 90, 100]) == 90
