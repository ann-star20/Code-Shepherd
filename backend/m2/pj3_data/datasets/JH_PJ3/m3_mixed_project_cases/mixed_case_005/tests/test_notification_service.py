import pytest
from app.notification_service import send_bulk_notification, format_message


def test_send_bulk_normal():
    result = send_bulk_notification([1, 2], "Hello!")
    assert len(result) == 2
    assert result[0]["status"] == "sent"


def test_format_message_normal():
    result = format_message("Hi {name}!", "Alice")
    assert result == "Hi Alice!"

# format_message: None, 빈 문자열 케이스 없음 → TEST-003
# retry_failed, get_sent_count 테스트 없음 → TEST-001
