"""TDD: normalize_github_repo — 입력 형식 정규화 & 유효성 검사."""

import pytest

from app.services.team_utils import normalize_github_repo


# ---------------------------------------------------------------------------
# 정상 케이스
# ---------------------------------------------------------------------------

def test_owner_repo_format_passes():
    assert normalize_github_repo("owner/repo") == "owner/repo"


def test_full_https_url_extracted():
    """오늘 수정된 버그 — 전체 URL 입력 시 owner/repo 추출."""
    assert normalize_github_repo("https://github.com/akdlemfla24-dotcom/first_work") == "akdlemfla24-dotcom/first_work"


def test_full_url_with_git_suffix():
    assert normalize_github_repo("https://github.com/owner/repo.git") == "owner/repo"


def test_full_url_with_trailing_slash():
    assert normalize_github_repo("https://github.com/owner/repo/") == "owner/repo"


def test_http_url_also_accepted():
    assert normalize_github_repo("http://github.com/owner/repo") == "owner/repo"


def test_leading_trailing_whitespace_stripped():
    assert normalize_github_repo("  owner/repo  ") == "owner/repo"


def test_hyphen_dot_underscore_in_names():
    assert normalize_github_repo("my-org/my_repo.v2") == "my-org/my_repo.v2"


# ---------------------------------------------------------------------------
# 오류 케이스
# ---------------------------------------------------------------------------

def test_empty_string_raises():
    with pytest.raises(ValueError):
        normalize_github_repo("")


def test_no_slash_raises():
    with pytest.raises(ValueError):
        normalize_github_repo("just-a-name")


def test_only_slash_raises():
    with pytest.raises(ValueError):
        normalize_github_repo("/")


def test_three_segments_raises():
    """owner/repo/extra 형식은 거부."""
    with pytest.raises(ValueError):
        normalize_github_repo("owner/repo/extra")


def test_special_chars_raises():
    with pytest.raises(ValueError):
        normalize_github_repo("owner/repo name")


def test_non_github_url_raises():
    """gitlab.com 등 다른 도메인은 거부."""
    with pytest.raises(ValueError):
        normalize_github_repo("https://gitlab.com/owner/repo")
