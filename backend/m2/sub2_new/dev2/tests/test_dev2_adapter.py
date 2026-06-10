"""Dev2 Webhook 게이트웨이 어댑터 단위 테스트.

테스트 원칙 (CLAUDE.md §13):
    - 실제 DB / LLM / subprocess 없이 Mock 기반으로 동작
    - analyze_static / analyze_security 가 표준 Issue dict를 반환하는지 검증
    - PRContext 구조체를 가짜 ctx로 직접 생성
"""
from __future__ import annotations

import os
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── 경로 설정 ─────────────────────────────────────────────────────────────────
_HERE = Path(__file__).parent
_GW = _HERE.parent / "webhook-gateway_2"
_DEV2_PARENT = _HERE.parent.parent  # sub2_new/

for _p in (str(_GW), str(_DEV2_PARENT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# registry를 먼저 import (어댑터 등록 전에 clear 가능하도록)
from registry import PRContext, registered_agents, clear  # noqa: E402


# ── 픽스처 ────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_registry():
    """각 테스트 전후 레지스트리 초기화."""
    clear()
    yield
    clear()


@pytest.fixture()
def tmp_repo(tmp_path: Path) -> Path:
    """가짜 Python 파일이 있는 임시 레포 디렉터리."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "auth.py").write_text(
        "import os\n"
        "def login(user):\n"
        "    query = 'SELECT * FROM users WHERE name=' + user\n"  # 의도적 SQL 인젝션
        "    return query\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture()
def ctx_with_diff(tmp_repo: Path) -> PRContext:
    """pr_diff와 work_dir이 채워진 PRContext."""
    diff = (
        "diff --git a/src/auth.py b/src/auth.py\n"
        "--- /dev/null\n"
        "+++ b/src/auth.py\n"
        "@@ -0,0 +1,4 @@\n"
        "+import os\n"
        "+def login(user):\n"
        "+    query = 'SELECT * FROM users WHERE name=' + user\n"
        "+    return query\n"
    )
    return PRContext(
        repo_full_name="owner/repo",
        clone_url="https://github.com/owner/repo.git",
        pr_number=1,
        commit_sha="abc123",
        branch="feature/test",
        author="junior_dev",
        work_dir=str(tmp_repo),
        pr_diff=diff,
    )


@pytest.fixture()
def ctx_no_diff(tmp_repo: Path) -> PRContext:
    """pr_diff가 빈 PRContext (work_dir 전체 스캔 폴백)."""
    return PRContext(
        repo_full_name="owner/repo",
        clone_url="https://github.com/owner/repo.git",
        pr_number=2,
        commit_sha="def456",
        branch="feature/test2",
        work_dir=str(tmp_repo),
        pr_diff="",
    )


@pytest.fixture()
def ctx_empty_workdir() -> PRContext:
    """work_dir이 존재하지 않는 PRContext."""
    return PRContext(
        repo_full_name="owner/repo",
        clone_url="https://github.com/owner/repo.git",
        pr_number=3,
        commit_sha="ghi789",
        branch="feature/test3",
        work_dir="/nonexistent/path",
        pr_diff="",
    )


# ── 어댑터 등록 테스트 ─────────────────────────────────────────────────────────

class TestAdapterRegistration:
    def test_import_registers_two_agents(self):
        """dev2_adapter import 시 static_analysis + security_scan이 등록된다."""
        import agents.dev2_adapter  # noqa: F401
        names = [a.name for a in registered_agents()]
        assert "static_analysis" in names
        assert "security_scan" in names

    def test_registered_agents_are_callable(self):
        """등록된 에이전트 함수가 호출 가능한지 확인."""
        import agents.dev2_adapter  # noqa: F401
        for agent in registered_agents():
            assert callable(agent.fn)


# ── analyze_static 테스트 ─────────────────────────────────────────────────────

class TestAnalyzeStatic:
    def _get_analyze_static(self):
        import agents.dev2_adapter
        return agents.dev2_adapter.analyze_static

    def test_returns_list(self, ctx_with_diff):
        """반환값이 list 타입이어야 한다."""
        with patch("dev2.tools.python.pylint_tool.run_pylint", return_value=[]), \
             patch("dev2.tools.python.radon_tool.run_radon", return_value=[]):
            result = self._get_analyze_static()(ctx_with_diff)
        assert isinstance(result, list)

    def test_issue_has_required_fields(self, ctx_with_diff):
        """반환 이슈 dict가 표준 필드를 모두 포함해야 한다."""
        fake_issue = {
            "severity": "Major",
            "file": "src/auth.py",
            "line": 3,
            "message": "사용되지 않는 임포트",
            "rule_id": "SA-W0611",
            "suggestion": "Pylint: unused-import",
        }
        with patch("dev2.tools.python.pylint_tool.run_pylint", return_value=[fake_issue]), \
             patch("dev2.tools.python.radon_tool.run_radon", return_value=[]):
            result = self._get_analyze_static()(ctx_with_diff)

        assert len(result) == 1
        issue = result[0]
        for field in ("severity", "file", "line", "message", "rule_id", "suggestion", "_agent"):
            assert field in issue, f"필드 누락: {field}"

    def test_agent_tag_is_static_analysis(self, ctx_with_diff):
        """_agent 값이 'static_analysis'이어야 한다."""
        fake_issue = {"severity": "Minor", "file": "src/auth.py", "line": 1,
                      "message": "msg", "rule_id": "SA-X", "suggestion": "s"}
        with patch("dev2.tools.python.pylint_tool.run_pylint", return_value=[fake_issue]), \
             patch("dev2.tools.python.radon_tool.run_radon", return_value=[]):
            result = self._get_analyze_static()(ctx_with_diff)
        assert result[0]["_agent"] == "static_analysis"

    def test_empty_workdir_returns_empty(self, ctx_empty_workdir):
        """work_dir이 없으면 빈 리스트를 반환한다."""
        result = self._get_analyze_static()(ctx_empty_workdir)
        assert result == []

    def test_no_diff_falls_back_to_full_scan(self, ctx_no_diff):
        """pr_diff가 없어도 work_dir 전체 스캔으로 폴백한다."""
        with patch("dev2.tools.python.pylint_tool.run_pylint", return_value=[]), \
             patch("dev2.tools.python.radon_tool.run_radon", return_value=[]):
            result = self._get_analyze_static()(ctx_no_diff)
        assert isinstance(result, list)


# ── analyze_security 테스트 ───────────────────────────────────────────────────

class TestAnalyzeSecurity:
    def _get_analyze_security(self):
        import agents.dev2_adapter
        return agents.dev2_adapter.analyze_security

    def test_returns_list(self, ctx_with_diff):
        with patch("dev2.tools.python.bandit_tool.run_bandit", return_value=[]), \
             patch("dev2.tools.common.semgrep_tool.run_semgrep", return_value=[]):
            result = self._get_analyze_security()(ctx_with_diff)
        assert isinstance(result, list)

    def test_critical_issue_passthrough(self, ctx_with_diff):
        """Critical 이슈가 그대로 반환되는지 확인 (게이트웨이 판정에 중요)."""
        critical_issue = {
            "severity": "Critical",
            "file": "src/auth.py",
            "line": 3,
            "message": "SQL 인젝션 가능성",
            "rule_id": "SEC-B608",
            "suggestion": "파라미터 바인딩 사용",
        }
        with patch("dev2.tools.python.bandit_tool.run_bandit", return_value=[critical_issue]), \
             patch("dev2.tools.common.semgrep_tool.run_semgrep", return_value=[]):
            result = self._get_analyze_security()(ctx_with_diff)

        assert len(result) == 1
        assert result[0]["severity"] == "Critical"
        assert result[0]["_agent"] == "security_scan"

    def test_agent_tag_is_security_scan(self, ctx_with_diff):
        """_agent 값이 'security_scan'이어야 한다."""
        fake = {"severity": "Major", "file": "src/auth.py", "line": 1,
                "message": "msg", "rule_id": "SEC-X", "suggestion": "s"}
        with patch("dev2.tools.python.bandit_tool.run_bandit", return_value=[fake]), \
             patch("dev2.tools.common.semgrep_tool.run_semgrep", return_value=[]):
            result = self._get_analyze_security()(ctx_with_diff)
        assert result[0]["_agent"] == "security_scan"

    def test_empty_workdir_returns_empty(self, ctx_empty_workdir):
        result = self._get_analyze_security()(ctx_empty_workdir)
        assert result == []

    def test_multiple_issues_all_tagged(self, ctx_with_diff):
        """여러 이슈가 반환될 때 모두 _agent 태그가 붙는지 확인."""
        issues = [
            {"severity": "Critical", "file": "src/auth.py", "line": 3,
             "message": "SQL 인젝션", "rule_id": "SEC-B608", "suggestion": "바인딩 사용"},
            {"severity": "Minor", "file": "src/auth.py", "line": 1,
             "message": "import os 미사용", "rule_id": "SEC-B101", "suggestion": "제거"},
        ]
        with patch("dev2.tools.python.bandit_tool.run_bandit", return_value=issues), \
             patch("dev2.tools.common.semgrep_tool.run_semgrep", return_value=[]):
            result = self._get_analyze_security()(ctx_with_diff)

        assert len(result) == 2
        assert all(r["_agent"] == "security_scan" for r in result)


# ── 헬퍼 함수 테스트 ──────────────────────────────────────────────────────────

class TestHelpers:
    def test_extract_changed_files_filters_unsupported(self, tmp_repo):
        """diff에서 지원 확장자(.py) 파일만 추출된다."""
        from agents.dev2_adapter import _extract_changed_files

        # .md는 지원 안 됨, .py는 지원
        (tmp_repo / "src" / "README.md").write_text("hello", encoding="utf-8")
        diff = (
            "+++ b/src/README.md\n"
            "+++ b/src/auth.py\n"
        )
        result = _extract_changed_files(diff, str(tmp_repo))
        paths = [os.path.basename(f) for f in result]
        assert "auth.py" in paths
        assert "README.md" not in paths

    def test_extract_changed_files_excludes_missing(self, tmp_repo):
        """diff에 있어도 실제 파일이 없으면 제외된다."""
        from agents.dev2_adapter import _extract_changed_files

        diff = "+++ b/src/nonexistent.py\n"
        result = _extract_changed_files(diff, str(tmp_repo))
        assert result == []

    def test_collect_all_files_returns_supported(self, tmp_repo):
        """work_dir 전체 스캔 시 지원 확장자 파일만 반환된다."""
        from agents.dev2_adapter import _collect_all_files

        (tmp_repo / "src" / "ignored.txt").write_text("x", encoding="utf-8")
        result = _collect_all_files(str(tmp_repo))
        exts = {Path(f).suffix.lower() for f in result}
        assert ".txt" not in exts
        assert ".py" in exts
