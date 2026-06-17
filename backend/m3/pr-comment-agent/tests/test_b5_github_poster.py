"""B5: github_poster.py — GitHub PR 코멘트 등록 또는 dry-run."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

import github_poster
from github_poster import post_comment, GithubPosterError


PR_URL = "https://github.com/acme/myrepo/pull/42"
COMMENT = "## 🤖 자동 리뷰\n\n테스트 코멘트입니다."


# ── URL 파싱 ──────────────────────────────────────────────────────────────────

class TestParsePrUrl:
    def test_valid_url_parsed(self):
        """표준 GitHub PR URL → (owner, repo, pr_num) 추출."""
        from github_poster import _parse_pr_url
        owner, repo, pr_num = _parse_pr_url(PR_URL)
        assert owner == "acme"
        assert repo == "myrepo"
        assert pr_num == 42

    def test_invalid_url_raises(self):
        """잘못된 URL → ValueError."""
        from github_poster import _parse_pr_url
        with pytest.raises(ValueError, match="Invalid PR URL"):
            _parse_pr_url("https://example.com/not-a-pr")


# ── 빈/공백 코멘트 → 건너뜀 ──────────────────────────────────────────────────

class TestEmptyComment:
    def test_empty_string_skipped(self):
        """빈 문자열 → 등록 시도 없이 skipped 반환."""
        result = post_comment(PR_URL, "")
        assert result["mode"] == "skipped"

    def test_whitespace_only_skipped(self):
        """공백만 있는 코멘트 → skipped."""
        result = post_comment(PR_URL, "   \n  ")
        assert result["mode"] == "skipped"

    def test_skipped_does_not_call_github(self):
        """skipped 시 GitHub API 호출 없음."""
        with patch.object(github_poster, "_post_to_github") as mock_post:
            post_comment(PR_URL, "")
            mock_post.assert_not_called()

    def test_skipped_does_not_create_dry_run_file(self):
        """skipped 시 dry-run 파일도 생성 안 함."""
        with patch.object(github_poster, "_dry_run") as mock_dry:
            post_comment(PR_URL, "")
            mock_dry.assert_not_called()


# ── 토큰 있음 → GitHub API 호출 ───────────────────────────────────────────────

class TestTokenPresent:
    def test_routes_to_github_when_token_set(self):
        """GITHUB_TOKEN 있음 → _post_to_github 호출."""
        with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_test"}):
            with patch.object(
                github_poster,
                "_post_to_github",
                return_value={"mode": "github", "comment_id": 99},
            ) as mock_post:
                result = post_comment(PR_URL, COMMENT)
                mock_post.assert_called_once_with("acme", "myrepo", 42, COMMENT, "ghp_test")
                assert result["mode"] == "github"
                assert result["comment_id"] == 99

    def test_post_to_github_sends_correct_request(self):
        """_post_to_github가 GitHub API에 올바른 요청 전송."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.ok = True
        mock_response.json.return_value = {"id": 777}

        with patch("github_poster.requests.post", return_value=mock_response) as mock_req:
            from github_poster import _post_to_github
            result = _post_to_github("acme", "myrepo", 42, COMMENT, "ghp_token")

            mock_req.assert_called_once()
            call_kwargs = mock_req.call_args
            # URL 확인
            assert "acme/myrepo" in call_kwargs[0][0]
            assert "42" in call_kwargs[0][0]
            # body 확인
            assert call_kwargs[1]["json"]["body"] == COMMENT
            # 결과 확인
            assert result["mode"] == "github"
            assert result["comment_id"] == 777

    def test_401_raises_clear_error(self):
        """401 응답 → GithubPosterError with '401' in message."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.ok = False

        with patch("github_poster.requests.post", return_value=mock_response):
            from github_poster import _post_to_github
            with pytest.raises(GithubPosterError) as exc_info:
                _post_to_github("acme", "myrepo", 42, COMMENT, "bad_token")
            assert "401" in str(exc_info.value)

    def test_other_http_error_raises(self):
        """500 같은 다른 오류도 GithubPosterError 발생."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.ok = False
        mock_response.text = "Internal Server Error"

        with patch("github_poster.requests.post", return_value=mock_response):
            from github_poster import _post_to_github
            with pytest.raises(GithubPosterError, match="500"):
                _post_to_github("acme", "myrepo", 42, COMMENT, "token")


# ── 토큰 없음 → dry-run ───────────────────────────────────────────────────────

class TestNoToken:
    def test_routes_to_dry_run_when_no_token(self):
        """GITHUB_TOKEN 없음 → _dry_run 호출."""
        # GITHUB_TOKEN 제거
        env_backup = os.environ.pop("GITHUB_TOKEN", None)
        try:
            with patch.object(
                github_poster,
                "_dry_run",
                return_value={"mode": "dry_run", "path": ".dry_run_comments/PR-42.md"},
            ) as mock_dry:
                result = post_comment(PR_URL, COMMENT)
                mock_dry.assert_called_once_with(42, COMMENT)
                assert result["mode"] == "dry_run"
        finally:
            if env_backup is not None:
                os.environ["GITHUB_TOKEN"] = env_backup

    def test_dry_run_creates_file(self, tmp_path, monkeypatch):
        """_dry_run → .dry_run_comments/PR-{n}.md 파일 생성."""
        monkeypatch.chdir(tmp_path)
        from github_poster import _dry_run

        result = _dry_run(42, COMMENT)

        assert result["mode"] == "dry_run"
        created_path = Path(result["path"])
        assert created_path.exists()
        assert created_path.read_text(encoding="utf-8") == COMMENT

    def test_dry_run_filename_includes_pr_number(self, tmp_path, monkeypatch):
        """dry-run 파일명에 PR 번호 포함."""
        monkeypatch.chdir(tmp_path)
        from github_poster import _dry_run

        result = _dry_run(99, "content")
        assert "PR-99" in result["path"]

    def test_dry_run_directory_created(self, tmp_path, monkeypatch):
        """dry-run 시 .dry_run_comments 디렉토리 자동 생성."""
        monkeypatch.chdir(tmp_path)
        from github_poster import _dry_run

        _dry_run(1, "some comment")
        assert (tmp_path / ".dry_run_comments").is_dir()
