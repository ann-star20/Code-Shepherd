"""prepare/repo.py — shallow clone + git checkout(commit_sha).

Windows .git read-only 회피: tempfile.mkdtemp으로 격리 작업 폴더를 생성.
흐름:
  1. git clone --depth 1 <url> <work_dir>
  2. commit_sha가 있으면: git -C <work_dir> fetch --depth 1 origin <sha>
  3.                      git -C <work_dir> checkout <sha>
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from contracts import RepoInfo


def prepare_repo(repo: RepoInfo) -> str:
    """레포를 shallow clone하고 commit_sha로 체크아웃한 뒤 작업 폴더 경로를 반환한다."""
    work_dir = tempfile.mkdtemp(prefix="dev3_repo_")

    _run_git(["git", "clone", "--depth", "1", repo.clone_url, work_dir], step="clone")

    if repo.commit_sha:
        _run_git(
            ["git", "-C", work_dir, "fetch", "--depth", "1", "origin", repo.commit_sha],
            step="fetch",
        )
        _run_git(
            ["git", "-C", work_dir, "checkout", repo.commit_sha],
            step="checkout",
        )

    return work_dir


def _run_git(cmd: list[str], step: str) -> None:
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"git {step} failed (exit {result.returncode}): "
            f"{result.stderr.decode(errors='replace').strip()}"
        )
