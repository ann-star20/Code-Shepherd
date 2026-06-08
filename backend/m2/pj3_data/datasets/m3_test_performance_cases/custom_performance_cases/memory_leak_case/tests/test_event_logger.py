from app.event_logger import clear_events_for_test, get_event_count, log_request_event


def test_log_request_event():
    clear_events_for_test()
    count = log_request_event(
        user_id=1,
        path="/api/orders",
        payload={"order_id": 10},
    )
    assert count == 1
    assert get_event_count() == 1
