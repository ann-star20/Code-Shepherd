"""Policy as Data — coverage 기준이 DB(policy_store)에서 오고, 없으면 fallback.

판정 로직(coverage.py)은 그대로. 바뀌는 건 "기준값이 오는 곳"뿐.
"""
import json
import textwrap
from pathlib import Path

import pytest

from config import conventions, policy_store


@pytest.fixture(autouse=True)
def _reset_cache():
    policy_store.reset_cache()
    yield
    policy_store.reset_cache()


# ─── 1) DB 없으면 하드코딩 fallback 그대로 ────────────────────────────────────
def test_coverage_rules_fallback_without_db(monkeypatch):
    monkeypatch.setattr(policy_store, "get_params", lambda k: None)
    rules = conventions.coverage_rules()
    assert rules == conventions.COVERAGE_RULES          # 하드코딩 fallback
    assert conventions.threshold_for("src/payment/x.py") == 0.90


# ─── 2) DB 정책이 있으면 그 값으로 판정(코드 수정 없이 기준 변경) ─────────────
def test_coverage_rules_from_db(monkeypatch):
    db_rules = {"default": 0.85, "payment": 0.95, "legacy": 0.60}
    monkeypatch.setattr(policy_store, "get_params",
                        lambda k: db_rules if k == "coverage" else None)
    rules = conventions.coverage_rules()
    assert rules["default"] == 0.85
    assert conventions.threshold_for("src/payment/billing.py") == 0.95   # DB값
    assert conventions.threshold_for("src/legacy/old.py") == 0.60
    assert conventions.threshold_for("src/util/x.py") == 0.85            # default


# ─── 3) DB params에 'default' 없으면 깨진 데이터 → fallback (안전) ────────────
def test_coverage_rules_ignores_invalid_db(monkeypatch):
    monkeypatch.setattr(policy_store, "get_params", lambda k: {"payment": 0.99})
    rules = conventions.coverage_rules()
    assert rules == conventions.COVERAGE_RULES          # default 없음 → fallback


# ─── 4) measure()가 DB 기준으로 판정 (end-to-end, DB는 mock) ──────────────────
def _write_cov(tmp_path, file_pct: float):
    cov = {
        "meta": {"branch_coverage": False},
        "totals": {"num_statements": 100, "percent_covered": file_pct},
        "files": {"src/util/x.py": {"summary": {"num_statements": 100,
                                                "percent_covered": file_pct}}},
    }
    (tmp_path / "coverage.json").write_text(json.dumps(cov), encoding="utf-8")


def test_measure_uses_db_default_threshold(tmp_path, monkeypatch):
    # DB default=0.50 이면 60%는 통과(이슈 없음). 하드코딩 0.80이었다면 이슈 떴을 것.
    monkeypatch.setattr(policy_store, "get_params",
                        lambda k: {"default": 0.50} if k == "coverage" else None)
    _write_cov(tmp_path, 60.0)
    from test_verification.coverage import measure
    issues, metrics = measure(str(tmp_path))
    assert metrics["coverage_line"] == 0.60
    assert issues == []        # 60% >= DB기준 50% → 이슈 없음
