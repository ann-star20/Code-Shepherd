# Notification Service
# Issues: PERF-002 (N+1), PERF-003 (memory leak), TEST-001 (low coverage), TEST-003 (edge case missing)

_sent_log: list = []  # PERF-003: 전역 리스트 무제한 누적


class UserRepository:
    def find_by_id(self, user_id: int) -> dict:
        return {"id": user_id, "email": f"user{user_id}@example.com", "active": True}


repo = UserRepository()


def send_bulk_notification(user_ids: list[int], message: str) -> list[dict]:
    """PERF-002: 루프마다 DB 호출 + PERF-003: 전역 로그 누적."""
    results = []
    for user_id in user_ids:
        user = repo.find_by_id(user_id)          # N+1
        if user["active"]:
            _sent_log.append({"to": user["email"], "msg": message})  # PERF-003
            results.append({"user_id": user_id, "status": "sent"})
    return results


def format_message(template: str, name: str) -> str:
    """TEST-003: name이 None, 빈 문자열, 매우 긴 문자열일 때 테스트 없음."""
    return template.replace("{name}", name)


def retry_failed(failed_ids: list[int], message: str) -> list[dict]:
    """TEST-001: 이 함수는 테스트가 없다."""
    return send_bulk_notification(failed_ids, message)


def get_sent_count() -> int:
    """TEST-001: 이 함수도 테스트가 없다."""
    return len(_sent_log)
