# Profile Service
# Issues: TEST-003 (edge case missing), TEST-004 (untested function), PERF-003 (memory leak)

_request_log: list = []  # PERF-003: 전역 리스트에 무제한 누적


def get_profile(user_id: int) -> dict:
    """TEST-003: 정상 입력만 테스트됨 — None, 음수, 0 케이스 없음."""
    if user_id <= 0:
        raise ValueError("user_id must be positive")
    return {"id": user_id, "name": f"user_{user_id}", "bio": ""}


def update_bio(user_id: int, bio: str) -> dict:
    """TEST-003: bio가 빈 문자열, None, 매우 긴 문자열일 때 테스트 없음."""
    if bio is None:
        bio = ""
    _request_log.append({"action": "update_bio", "user_id": user_id})  # PERF-003
    return {"id": user_id, "bio": bio}


def update_avatar(user_id: int, image_data: bytes) -> dict:
    """TEST-004: 이 함수는 테스트가 전혀 없다."""
    if not image_data:
        raise ValueError("image_data cannot be empty")
    _request_log.append({"action": "update_avatar", "user_id": user_id})  # PERF-003
    return {"id": user_id, "avatar": "updated"}


def delete_account(user_id: int, confirm: bool) -> bool:
    """TEST-004: 이 함수도 테스트가 없다."""
    if not confirm:
        return False
    _request_log.append({"action": "delete", "user_id": user_id})  # PERF-003
    return True
