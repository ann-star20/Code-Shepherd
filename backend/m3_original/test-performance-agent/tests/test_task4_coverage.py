"""Task 4 — test_verification/coverage.py TDD 테스트.

긍정 케이스 + PRD §5.4 부정 케이스 + def-line 함정 포함.
"""
import json
from pathlib import Path

import pytest

SAMPLE_REPO = Path(__file__).parent / "fixtures" / "sample_repo"


# ── 긍정 케이스 ────────────────────────────────────────────────────────────

def test_line_20pct_produces_major_issue():
    """라인 20% → TEST-001 Major 이슈 1개."""
    from test_verification.coverage import measure
    issues, metrics = measure(str(SAMPLE_REPO))
    assert len(issues) == 1
    assert issues[0].rule_id == "TEST-001"
    assert issues[0].severity == "Major"


def test_line_20pct_metric_correct():
    """라인 20% → metrics['coverage_line'] ≈ 0.20."""
    from test_verification.coverage import measure
    _, metrics = measure(str(SAMPLE_REPO))
    assert metrics is not None
    assert abs(metrics["coverage_line"] - 0.20) < 0.01


def test_line_90pct_no_issue(tmp_path):
    """라인 90% → 이슈 0개 (메트릭만 남김)."""
    cov = {
        "meta": {"format": 3, "branch_coverage": False},
        "files": {},
        "totals": {
            "covered_lines": 90,
            "num_statements": 100,
            "percent_covered": 90.0,
        },
    }
    (tmp_path / "coverage.json").write_text(json.dumps(cov), encoding="utf-8")
    from test_verification.coverage import measure
    issues, metrics = measure(str(tmp_path))
    assert issues == []
    assert metrics is not None
    assert abs(metrics["coverage_line"] - 0.90) < 0.01


def test_branch_data_produces_coverage_branch(tmp_path):
    """branch 데이터 있음 → metrics에 'coverage_branch' 키 포함."""
    cov = {
        "meta": {"format": 3, "branch_coverage": True},
        "files": {},
        "totals": {
            "covered_lines": 80,
            "num_statements": 100,
            "percent_covered": 80.0,
            "covered_branches": 40,
            "num_branches": 50,
        },
    }
    (tmp_path / "coverage.json").write_text(json.dumps(cov), encoding="utf-8")
    from test_verification.coverage import measure
    _, metrics = measure(str(tmp_path))
    assert metrics is not None
    assert "coverage_branch" in metrics
    assert abs(metrics["coverage_branch"] - 0.8) < 0.01


# ── 부정 케이스 (PRD §5.4) ─────────────────────────────────────────────────

def test_no_coverage_json_returns_empty(tmp_path):
    """coverage.json 없음 → ([], None) — 정직성 원칙."""
    from test_verification.coverage import measure
    issues, metrics = measure(str(tmp_path))
    assert issues == []
    assert metrics is None


def test_num_statements_zero_returns_none(tmp_path):
    """num_statements=0 → metrics=None (NaN/ZeroDivision 금지)."""
    cov = {
        "meta": {"format": 3, "branch_coverage": False},
        "files": {},
        "totals": {
            "covered_lines": 0,
            "num_statements": 0,
            "percent_covered": 0.0,
        },
    }
    (tmp_path / "coverage.json").write_text(json.dumps(cov), encoding="utf-8")
    from test_verification.coverage import measure
    issues, metrics = measure(str(tmp_path))
    assert issues == []
    assert metrics is None


def test_no_branch_data_excludes_coverage_branch_key(tmp_path):
    """branch 데이터 없으면 'coverage_branch' 키 자체를 제외 (null로 두지 말 것)."""
    cov = {
        "meta": {"format": 3, "branch_coverage": False},
        "files": {},
        "totals": {
            "covered_lines": 80,
            "num_statements": 100,
            "percent_covered": 80.0,
        },
    }
    (tmp_path / "coverage.json").write_text(json.dumps(cov), encoding="utf-8")
    from test_verification.coverage import measure
    _, metrics = measure(str(tmp_path))
    assert metrics is not None
    assert "coverage_branch" not in metrics


# ── def-line 함정 케이스 ────────────────────────────────────────────────────

def test_func_coverage_def_line_trap():
    """def-line만 실행이면 func covered로 잘못 계산 금지.

    sample_repo/src/posts.py 실행 흔적:
      executed_lines = [4, 12, 13, 16]
      - get_posts   def=4  body=5~9  → 본문 미실행 → uncovered
      - calc_discount def=12 body=13  → 본문 실행   → covered
      - find_dups   def=16 body=17~22 → 본문 미실행 → uncovered

    naive(def-line 체크) 방법이면 3/3=1.0 → 버그.
    올바른 구현은 1/total ≈ 0.25~0.34 (< 0.5).
    """
    from test_verification.coverage import measure
    _, metrics = measure(str(SAMPLE_REPO))
    assert metrics is not None
    func_cov = metrics.get("coverage_func")
    assert func_cov is not None, "coverage_func 키가 metrics에 없음"
    assert func_cov < 0.5, (
        f"def-line 함정 미방어: coverage_func={func_cov} (기대값 < 0.5)"
    )
