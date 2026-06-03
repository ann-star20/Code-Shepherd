from app.report_service import find_duplicate_pairs


def test_find_duplicate_pairs():
    users = [
        {"id": 1, "email": "a@example.com"},
        {"id": 2, "email": "b@example.com"},
        {"id": 3, "email": "a@example.com"},
    ]
    result = find_duplicate_pairs(users)
    assert (1, 3) in result or (3, 1) in result
