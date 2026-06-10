"""SESSION 8C — verdict 정확도 벤치마크 (scoring 로직 TDD).

verdict 정확도 = 사람이 부여한 expected_verdict 와 실제 aggregate() 가 산출한 verdict 의 일치율.
여기서는 scoring 로직(집계·일치율·불일치 목록)을 합성 케이스로 검증한다.
실 라벨셋(8B 재사용 + 확장) 자체의 결과는 validation/verdict_benchmark.py 가 산출한다.
"""
from __future__ import annotations

import pytest

from validation.verdict_benchmark import (
    CASES,
    build_outputs,
    compute_verdict,
    score_cases,
)


# ── compute_verdict: 케이스 issue-set → 실제 aggregate verdict ──────────────────

class TestComputeVerdict:
    def test_one_major_is_lgtm(self):
        case = {"name": "c", "issues": [("Major", "PERF-002", "a.py")],
                "expected_verdict": "lgtm"}
        assert compute_verdict(case) == "lgtm"

    def test_three_major_is_rework(self):
        case = {"name": "c", "issues": [("Major", "PERF-002", "a.py")] * 3,
                "expected_verdict": "rework"}
        assert compute_verdict(case) == "rework"

    def test_one_critical_is_escalate(self):
        case = {"name": "c", "issues": [("Critical", "SEC-001", "a.py")],
                "expected_verdict": "escalate"}
        assert compute_verdict(case) == "escalate"

    def test_many_minor_is_lgtm(self):
        case = {"name": "c", "issues": [("Minor", "TEST-003", "a.py")] * 5,
                "expected_verdict": "lgtm"}
        assert compute_verdict(case) == "lgtm"

    def test_empty_is_lgtm(self):
        assert compute_verdict({"name": "c", "issues": [], "expected_verdict": "lgtm"}) == "lgtm"


# ── build_outputs: 같은 (rule,file) 다수 라벨이 dedup 으로 사라지지 않아야 함 ──

class TestBuildOutputs:
    def test_repeated_rule_file_not_deduped(self):
        """동일 (rule_id, file) 라벨 3개 → 서로 다른 line 부여로 3건 모두 보존."""
        outs = build_outputs([("Minor", "TEST-003", "a.py")] * 3)
        total = sum(len(o.issues) for o in outs)
        assert total == 3


# ── score_cases: 일치율·불일치 목록 집계 ────────────────────────────────────────

class TestScoreCases:
    def _cases(self):
        return [
            {"name": "ok_lgtm", "issues": [("Major", "R", "a.py")],
             "expected_verdict": "lgtm"},                     # computed lgtm → match
            {"name": "ok_rework", "issues": [("Major", "R", "a.py")] * 3,
             "expected_verdict": "rework"},                   # computed rework → match
            {"name": "miss", "issues": [("Critical", "R", "a.py")],
             "expected_verdict": "lgtm"},                     # computed escalate → mismatch
        ]

    def test_counts_and_rate(self):
        result = score_cases(self._cases())
        assert result["n"] == 3
        assert result["match"] == 2
        assert result["match_rate"] == pytest.approx(2 / 3)

    def test_per_case_has_expected_and_computed(self):
        result = score_cases(self._cases())
        by_name = {r["name"]: r for r in result["per_case"]}
        assert by_name["miss"]["expected"] == "lgtm"
        assert by_name["miss"]["computed"] == "escalate"
        assert by_name["miss"]["ok"] is False
        assert by_name["ok_lgtm"]["ok"] is True

    def test_mismatches_listed(self):
        result = score_cases(self._cases())
        names = [m["name"] for m in result["mismatches"]]
        assert names == ["miss"]

    def test_empty_cases_zero_rate(self):
        result = score_cases([])
        assert result["n"] == 0
        assert result["match_rate"] == 0.0


# ── 실 라벨셋: 8B 재사용 + 확장, 3개 verdict 모두 커버, ≥10건 ───────────────────

class TestRealLabelset:
    def test_at_least_ten_cases(self):
        assert len(CASES) >= 10

    def test_covers_all_three_verdicts(self):
        expected = {c["expected_verdict"] for c in CASES}
        assert {"lgtm", "rework", "escalate"} <= expected

    def test_every_case_has_required_fields(self):
        for c in CASES:
            assert c["expected_verdict"] in ("lgtm", "rework", "escalate")
            assert "issues" in c and "name" in c

    def test_score_runs_on_real_cases(self):
        result = score_cases(CASES)
        assert result["n"] == len(CASES)
        assert 0.0 <= result["match_rate"] <= 1.0
