"""Task 18 (SESSION 8B) — rule별 Precision/Recall/F1 채점기 TDD.

기존 eval.evaluate(recall/false_alarm, 골든1건)를 계승·세분화한
evaluate_prf(cases) 를 테스트한다. 매칭 기준은 기존과 동일한 (rule_id, file) 멀티셋.

검증 시나리오:
  1. 완전일치       → 각 rule P=R=F1=1.0
  2. 일부 놓침(FN)  → 해당 rule recall<1, fn_list 기록
  3. 헛다리(FP)     → 해당 rule precision<1, fp_list 기록
  4. 전부 오탐      → 음성 케이스(expected 0, output>0) → precision 하락
  5. 전부 놓침      → recall=0
  6. 음성 케이스 정상(expected 0, output 0) → FP 없음
  7. 다건 집계      → overall = rule 합산
  8. F1 = 조화평균
  9. PASS/FAIL 판정 (overall F1 합격선)
"""
from pathlib import Path

import pytest

from contracts import AgentOutput, Issue, SummaryCount
from validation.eval import evaluate_prf


# ── 헬퍼 ────────────────────────────────────────────────────

def _issue(rule_id: str, file: str, line=None) -> Issue:
    sev = "Major" if rule_id in ("TEST-001", "PERF-002") else "Minor"
    return Issue(severity=sev, file=file, line=line, message=f"{rule_id}@{file}", rule_id=rule_id)


def _output(agent: str, issues: list[Issue]) -> AgentOutput:
    return AgentOutput(
        task_id="t", scan_id=1, pr_id="PR-1", agent=agent, issues=issues,
        summary=SummaryCount(
            critical=sum(1 for i in issues if i.severity == "Critical"),
            major=sum(1 for i in issues if i.severity == "Major"),
            minor=sum(1 for i in issues if i.severity == "Minor"),
        ),
    )


def _expected(tv: list[dict], perf: list[dict]) -> dict:
    return {
        "test_verification": {"expected_issues": tv},
        "performance": {"expected_issues": perf},
    }


def _case(name: str, tv_out: list[Issue], perf_out: list[Issue],
          tv_exp: list[dict], perf_exp: list[dict]) -> dict:
    return {
        "name": name,
        "outputs": [_output("test_verification", tv_out), _output("performance", perf_out)],
        "expected": _expected(tv_exp, perf_exp),
    }


# ── 1. 완전일치 ──────────────────────────────────────────────

def test_perfect_match_all_rules_f1_1():
    case = _case(
        "perfect",
        tv_out=[_issue("TEST-001", "(전체)"), _issue("TEST-004", "src/a.py", 4)],
        perf_out=[_issue("PERF-002", "src/a.py", 7), _issue("PERF-001", "src/a.py", 16)],
        tv_exp=[{"rule_id": "TEST-001", "file": "(전체)"}, {"rule_id": "TEST-004", "file": "src/a.py"}],
        perf_exp=[{"rule_id": "PERF-002", "file": "src/a.py"}, {"rule_id": "PERF-001", "file": "src/a.py"}],
    )
    r = evaluate_prf([case])
    for rule in ("TEST-001", "TEST-004", "PERF-002", "PERF-001"):
        assert r["per_rule"][rule]["precision"] == 1.0
        assert r["per_rule"][rule]["recall"] == 1.0
        assert r["per_rule"][rule]["f1"] == 1.0
    assert r["overall"]["f1"] == 1.0
    assert r["fp_list"] == []
    assert r["fn_list"] == []


# ── 2. 일부 놓침(FN) ─────────────────────────────────────────

def test_missing_expected_drops_recall_and_lists_fn():
    case = _case(
        "miss",
        tv_out=[_issue("TEST-004", "src/a.py", 4)],          # get 1, miss 1
        perf_out=[],
        tv_exp=[{"rule_id": "TEST-004", "file": "src/a.py"},
                {"rule_id": "TEST-004", "file": "src/b.py"}],
        perf_exp=[],
    )
    r = evaluate_prf([case])
    pr = r["per_rule"]["TEST-004"]
    assert pr["recall"] == 0.5          # 1 of 2
    assert pr["precision"] == 1.0       # the 1 output was correct
    assert pr["fn"] == 1
    assert any(f["rule_id"] == "TEST-004" and f["file"] == "src/b.py" for f in r["fn_list"])


# ── 3. 헛다리(FP) ────────────────────────────────────────────

def test_extra_output_drops_precision_and_lists_fp():
    case = _case(
        "fp",
        tv_out=[_issue("TEST-004", "src/a.py", 4), _issue("TEST-004", "src/ghost.py", 9)],
        perf_out=[],
        tv_exp=[{"rule_id": "TEST-004", "file": "src/a.py"}],
        perf_exp=[],
    )
    r = evaluate_prf([case])
    pr = r["per_rule"]["TEST-004"]
    assert pr["recall"] == 1.0
    assert pr["precision"] == 0.5       # 1 of 2 outputs correct
    assert pr["fp"] == 1
    assert any(f["rule_id"] == "TEST-004" and f["file"] == "src/ghost.py" for f in r["fp_list"])


# ── 4. 음성 케이스: expected 0, output>0 → precision 하락 ─────

def test_negative_case_false_positive():
    case = _case(
        "clean_but_flagged",
        tv_out=[_issue("TEST-003", "src/clean.py", 1)],   # heuristic over-fire
        perf_out=[],
        tv_exp=[],
        perf_exp=[],
    )
    r = evaluate_prf([case])
    pr = r["per_rule"]["TEST-003"]
    assert pr["fp"] == 1
    assert pr["tp"] == 0
    assert pr["precision"] == 0.0
    assert r["n_negative"] == 1


# ── 5. 전부 놓침 → recall 0 ──────────────────────────────────

def test_all_missed_recall_zero():
    case = _case(
        "all_missed",
        tv_out=[], perf_out=[],
        tv_exp=[{"rule_id": "TEST-001", "file": "(전체)"}],
        perf_exp=[],
    )
    r = evaluate_prf([case])
    assert r["per_rule"]["TEST-001"]["recall"] == 0.0
    assert r["per_rule"]["TEST-001"]["fn"] == 1


# ── 6. 음성 케이스 정상(0/0) → FP 없음 ───────────────────────

def test_negative_clean_no_false_positive():
    case = _case("truly_clean", tv_out=[], perf_out=[], tv_exp=[], perf_exp=[])
    r = evaluate_prf([case])
    assert r["fp_list"] == []
    assert r["overall"]["fp"] == 0
    assert r["n_negative"] == 1


# ── 7. 다건 집계 ─────────────────────────────────────────────

def test_multi_case_aggregation():
    c1 = _case("c1",
               tv_out=[_issue("TEST-004", "src/a.py", 4)], perf_out=[],
               tv_exp=[{"rule_id": "TEST-004", "file": "src/a.py"}], perf_exp=[])
    c2 = _case("c2",
               tv_out=[_issue("TEST-004", "src/b.py", 5)], perf_out=[],
               tv_exp=[{"rule_id": "TEST-004", "file": "src/b.py"}], perf_exp=[])
    r = evaluate_prf([c1, c2])
    assert r["per_rule"]["TEST-004"]["tp"] == 2
    assert r["per_rule"]["TEST-004"]["f1"] == 1.0
    assert r["n_cases"] == 2
    assert r["n_positive"] == 2


# ── 8. F1 = 조화평균 ─────────────────────────────────────────

def test_f1_is_harmonic_mean():
    # precision=0.5 (1 of 2 output correct), recall=1.0 → F1 = 2*0.5*1/(1.5) = 0.6667
    case = _case(
        "harmonic",
        tv_out=[_issue("TEST-004", "src/a.py", 4), _issue("TEST-004", "src/ghost.py", 9)],
        perf_out=[],
        tv_exp=[{"rule_id": "TEST-004", "file": "src/a.py"}],
        perf_exp=[],
    )
    r = evaluate_prf([case])
    pr = r["per_rule"]["TEST-004"]
    assert pr["precision"] == 0.5
    assert pr["recall"] == 1.0
    assert round(pr["f1"], 4) == 0.6667


# ── 9. PASS/FAIL 판정 ────────────────────────────────────────

def test_pass_fail_threshold():
    good = _case("good",
                 tv_out=[_issue("TEST-001", "(전체)")], perf_out=[],
                 tv_exp=[{"rule_id": "TEST-001", "file": "(전체)"}], perf_exp=[])
    r_pass = evaluate_prf([good], overall_f1_pass=0.9)
    assert r_pass["pass"] is True

    bad = _case("bad",
                tv_out=[_issue("TEST-004", "src/ghost.py", 9)], perf_out=[],
                tv_exp=[{"rule_id": "TEST-001", "file": "(전체)"}], perf_exp=[])
    r_fail = evaluate_prf([bad], overall_f1_pass=0.9)
    assert r_fail["pass"] is False
