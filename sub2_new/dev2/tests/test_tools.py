"""
Task 3 테스트 — CLI 도구 + 다국어 라우터

실제 CLI 도구(pylint, bandit 등)가 설치되어 있어야 통과한다.
CI 환경에서는 Docker 컨테이너 안에서 실행한다.

라우터 테스트는 도구 설치 불필요 (순수 Python 로직).
"""

import shutil
import pytest
from dev2.tools.python.pylint_tool import run_pylint
from dev2.tools.python.radon_tool import run_radon
from dev2.tools.python.bandit_tool import run_bandit
from dev2.tools.javascript.eslint_tool import run_eslint
from dev2.tools.common.semgrep_tool import run_semgrep
from dev2.tools.router import detect_languages, get_tools_for_file

# CLI 도구 가용성 체크 — 미설치 시 해당 테스트 skip (로컬 개발 환경 대응)
eslint_installed = shutil.which("eslint") is not None
semgrep_installed = shutil.which("semgrep") is not None


# ── Python 도구 테스트 ────────────────────────────────────────────────────────

def test_pylint_returns_issues():
    issues = run_pylint(["dev2/tests/fixtures/bad_code.py"])
    assert len(issues) > 0
    assert all(i["severity"] in ("Critical", "Major", "Minor") for i in issues)


def test_radon_detects_complexity():
    issues = run_radon(["dev2/tests/fixtures/bad_code.py"])
    assert any("순환복잡도" in i["message"] for i in issues)


def test_bandit_detects_sql_injection():
    issues = run_bandit(["dev2/tests/fixtures/vulnerable_code.py"])
    assert len(issues) > 0


# ── JavaScript 도구 테스트 ────────────────────────────────────────────────────

@pytest.mark.skipif(not eslint_installed, reason="eslint CLI 미설치 (Docker에서 실행)")
def test_eslint_returns_issues():
    issues = run_eslint(["dev2/tests/fixtures/bad_code.js"])
    assert len(issues) > 0
    assert all(i["severity"] in ("Critical", "Major", "Minor") for i in issues)


# ── 공통 보안 도구 테스트 (Semgrep) ─────────────────────────────────────────

@pytest.mark.skipif(not semgrep_installed, reason="semgrep CLI 미설치 (Docker에서 실행)")
def test_semgrep_detects_html_xss():
    issues = run_semgrep(["dev2/tests/fixtures/bad_code.html"], lang="html")
    assert len(issues) > 0


# ── 라우터 테스트 (도구 설치 불필요) ─────────────────────────────────────────

def test_router_detects_language():
    groups = detect_languages(["auth.py", "app.js", "index.html", "style.css"])
    assert "python" in groups
    assert "javascript" in groups
    assert "html" in groups
    assert "css" in groups


def test_router_unknown_extension():
    # 모르는 확장자 → semgrep만 실행
    _, static, security, _ = get_tools_for_file("file.rb")
    assert static == []
    assert "semgrep" in security


def test_router_typescript():
    groups = detect_languages(["component.tsx", "util.ts"])
    assert "typescript" in groups


def test_router_empty_list():
    groups = detect_languages([])
    assert groups == {}


def test_pylint_empty_input():
    # 빈 리스트 → 빈 결과 (예외 없음, CLAUDE.md §12)
    assert run_pylint([]) == []


def test_bandit_empty_input():
    assert run_bandit([]) == []


def test_semgrep_empty_input():
    assert run_semgrep([]) == []
