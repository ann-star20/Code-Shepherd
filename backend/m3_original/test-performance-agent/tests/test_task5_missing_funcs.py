"""Task 5 — test_verification/missing_funcs.py TDD 테스트.

긍정·부정 케이스 + ★ def-line 함정 반드시 포함 (PRD §5.4).
"""
import json
from pathlib import Path

import pytest

SAMPLE_REPO = Path(__file__).parent / "fixtures" / "sample_repo"


# ── 긍정 케이스 ────────────────────────────────────────────────────────────

def test_both_func_bodies_executed_zero_issues(tmp_path):
    """두 함수 본문 다 실행 → 0 issue."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "foo.py").write_text(
        "def add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a - b\n",
        encoding="utf-8",
    )
    # def lines (1, 4) + body lines (2, 5) 모두 실행
    cov = {
        "files": {"src/foo.py": {"executed_lines": [1, 2, 4, 5]}},
        "totals": {"num_statements": 4, "percent_covered": 100.0},
    }
    (tmp_path / "coverage.json").write_text(json.dumps(cov), encoding="utf-8")

    from test_verification.missing_funcs import detect
    issues = detect(str(tmp_path), {"src/foo.py": {1, 2, 4, 5}})
    assert issues == []


def test_one_func_body_not_executed_one_issue(tmp_path):
    """한 함수 본문 미실행 → 1 issue (그 함수만)."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "foo.py").write_text(
        "def add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a - b\n",
        encoding="utf-8",
    )
    # add body line 2 실행; sub body line 5 미실행
    cov = {
        "files": {"src/foo.py": {"executed_lines": [1, 2, 4]}},
        "totals": {"num_statements": 4, "percent_covered": 75.0},
    }
    (tmp_path / "coverage.json").write_text(json.dumps(cov), encoding="utf-8")

    from test_verification.missing_funcs import detect
    issues = detect(str(tmp_path), {"src/foo.py": {1, 2, 4, 5}})
    assert len(issues) == 1
    assert issues[0].rule_id == "TEST-004"
    assert issues[0].severity == "Minor"
    assert "sub" in issues[0].message


# ── ★ def-line 함정 케이스 ─────────────────────────────────────────────────

def test_def_line_only_both_funcs_flagged(tmp_path):
    """★ def 줄만 실행되고 본문 미실행 → 둘 다 잡혀야 함.

    naive 구현: def line이 executed_lines에 있으면 covered로 간주 → 0 이슈 (버그!)
    올바른 구현: body lines와 executed_lines 교집합으로 판정 → 2 이슈
    """
    src = tmp_path / "src"
    src.mkdir()
    (src / "foo.py").write_text(
        "def foo():\n    return 1\n\ndef bar():\n    return 2\n",
        encoding="utf-8",
    )
    # def lines (1, 4) 실행, body lines (2, 5) 미실행 — 함정 케이스
    cov = {
        "files": {"src/foo.py": {"executed_lines": [1, 4]}},
        "totals": {"num_statements": 4, "percent_covered": 50.0},
    }
    (tmp_path / "coverage.json").write_text(json.dumps(cov), encoding="utf-8")

    from test_verification.missing_funcs import detect
    issues = detect(str(tmp_path), {"src/foo.py": {1, 2, 4, 5}})
    assert len(issues) == 2, (
        f"def-line 함정 미방어 — naive=0 이슈, 올바른 구현=2 이슈: {issues}"
    )
    messages = [i.message for i in issues]
    assert any("foo" in m for m in messages)
    assert any("bar" in m for m in messages)


# ── 부정 케이스 (PRD §5.4) ─────────────────────────────────────────────────

def test_no_coverage_json_graceful(tmp_path):
    """coverage.json 없음 → graceful 0 (예외 없이 빈 리스트)."""
    from test_verification.missing_funcs import detect
    issues = detect(str(tmp_path), {"src/foo.py": {1, 2, 3}})
    assert issues == []
