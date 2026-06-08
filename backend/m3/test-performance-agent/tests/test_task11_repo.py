"""Task 11: prepare/repo.py — shallow clone + checkout(commit_sha) TDD."""
import subprocess
from unittest.mock import patch, MagicMock, call
import pytest

from prepare.repo import prepare_repo
from contracts import RepoInfo


# ──────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────

def _make_repo(clone_url="https://github.com/test/repo.git", commit_sha="abc123def456"):
    return RepoInfo(clone_url=clone_url, commit_sha=commit_sha)


def _ok():
    """subprocess.run 성공 반환값."""
    m = MagicMock()
    m.returncode = 0
    m.stdout = b""
    m.stderr = b""
    return m


# ──────────────────────────────────────────────
# Test 1: shallow clone → fetch → checkout 순서 검증
# ──────────────────────────────────────────────

def test_prepare_repo_calls_clone_fetch_checkout(tmp_path):
    """prepare_repo가 clone → fetch → checkout 순서로 subprocess를 호출한다."""
    repo = _make_repo()
    with patch("prepare.repo.subprocess.run", return_value=_ok()) as mock_run, \
         patch("prepare.repo.tempfile.mkdtemp", return_value=str(tmp_path)):
        result = prepare_repo(repo)

    calls = mock_run.call_args_list
    assert len(calls) == 3

    # 1) clone --depth 1
    clone_cmd = calls[0][0][0]
    assert clone_cmd[0] == "git"
    assert "clone" in clone_cmd
    assert "--depth" in clone_cmd
    assert "1" in clone_cmd
    assert repo.clone_url in clone_cmd

    # 2) fetch --depth 1 origin <sha>
    fetch_cmd = calls[1][0][0]
    assert "fetch" in fetch_cmd
    assert repo.commit_sha in fetch_cmd

    # 3) checkout <sha>
    checkout_cmd = calls[2][0][0]
    assert "checkout" in checkout_cmd
    assert repo.commit_sha in checkout_cmd


# ──────────────────────────────────────────────
# Test 2: 반환값이 문자열 경로여야 한다
# ──────────────────────────────────────────────

def test_prepare_repo_returns_string_path(tmp_path):
    """prepare_repo는 작업 폴더 경로(str)를 반환한다."""
    repo = _make_repo()
    with patch("prepare.repo.subprocess.run", return_value=_ok()), \
         patch("prepare.repo.tempfile.mkdtemp", return_value=str(tmp_path)):
        result = prepare_repo(repo)

    assert isinstance(result, str)
    assert len(result) > 0


# ──────────────────────────────────────────────
# Test 3: tempfile.mkdtemp으로 작업 디렉토리를 생성한다 (Windows .git read-only 회피)
# ──────────────────────────────────────────────

def test_prepare_repo_uses_tempfile_mkdtemp(tmp_path):
    """Windows .git read-only 문제 회피를 위해 tempfile.mkdtemp를 사용한다."""
    repo = _make_repo()
    with patch("prepare.repo.subprocess.run", return_value=_ok()) as mock_run, \
         patch("prepare.repo.tempfile.mkdtemp", return_value=str(tmp_path)) as mock_mkdtemp:
        prepare_repo(repo)

    mock_mkdtemp.assert_called_once()


# ──────────────────────────────────────────────
# Test 4: clone 실패 시 RuntimeError
# ──────────────────────────────────────────────

def test_prepare_repo_raises_on_clone_failure(tmp_path):
    """git clone 실패(returncode != 0) → RuntimeError."""
    repo = _make_repo()
    fail = MagicMock()
    fail.returncode = 128
    fail.stderr = b"fatal: repository not found"

    with patch("prepare.repo.subprocess.run", return_value=fail), \
         patch("prepare.repo.tempfile.mkdtemp", return_value=str(tmp_path)):
        with pytest.raises(RuntimeError, match="clone"):
            prepare_repo(repo)


# ──────────────────────────────────────────────
# Test 5: git -C <work_dir> fetch/checkout 형식 (분리 실행)
# ──────────────────────────────────────────────

def test_prepare_repo_uses_git_dash_C(tmp_path):
    """`git -C <work_dir> fetch/checkout` 형식으로 서브커맨드를 실행한다."""
    repo = _make_repo()
    with patch("prepare.repo.subprocess.run", return_value=_ok()) as mock_run, \
         patch("prepare.repo.tempfile.mkdtemp", return_value=str(tmp_path)):
        prepare_repo(repo)

    calls = mock_run.call_args_list
    fetch_cmd = calls[1][0][0]
    checkout_cmd = calls[2][0][0]

    # fetch/checkout은 git -C <dir> 형식이어야 함
    assert fetch_cmd[1] == "-C"
    assert checkout_cmd[1] == "-C"


# ──────────────────────────────────────────────
# Test 6: commit_sha 없으면 fetch/checkout 생략
# ──────────────────────────────────────────────

def test_prepare_repo_skips_fetch_when_no_sha(tmp_path):
    """commit_sha가 빈 문자열이면 fetch/checkout을 생략하고 경로만 반환한다."""
    repo = RepoInfo(clone_url="https://github.com/test/repo.git", commit_sha="")
    with patch("prepare.repo.subprocess.run", return_value=_ok()) as mock_run, \
         patch("prepare.repo.tempfile.mkdtemp", return_value=str(tmp_path)):
        result = prepare_repo(repo)

    # clone 1번만 호출 (fetch·checkout 생략)
    assert mock_run.call_count == 1
    assert isinstance(result, str)
