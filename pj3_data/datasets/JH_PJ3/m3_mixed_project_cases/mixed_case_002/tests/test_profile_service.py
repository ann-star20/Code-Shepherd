import pytest
from app.profile_service import get_profile, update_bio


def test_get_profile_normal():
    result = get_profile(1)
    assert result["id"] == 1

# None, 0, 음수 케이스 없음 → TEST-003
# update_avatar, delete_account 테스트 없음 → TEST-004
