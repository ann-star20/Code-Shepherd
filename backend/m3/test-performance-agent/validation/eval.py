"""골든 라벨 채점기 — expected_output.json 대비 recall / false_alarm 계산.

매칭 기준: (rule_id, file) 멀티셋.
  - rule_id + file 기준 멀티셋 교집합 → matched
  - recall       = matched / total_expected
  - false_alarm  = (total_output - matched) / total_output
  - PASS: recall >= 0.9 AND false_alarm <= FALSE_ALARM_THRESHOLD(0.10)

NOTE: line 번호는 식별자가 아닌 참고값으로 취급한다.
  (예: PERF-001은 expected=16, 실제=18 — rule_id+file로 일치)
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

# 스크립트 직접 실행 시 프로젝트 루트를 sys.path에 추가
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config.settings import (  # noqa: E402
    FALSE_ALARM_THRESHOLD,
    OVERALL_F1_PASS_THRESHOLD,
    RULE_F1_MIN_THRESHOLD,
)
from contracts import AgentOutput  # noqa: E402

_RECALL_PASS_THRESHOLD = 0.9
_AGENT_KEYS = ("test_verification", "performance")


def evaluate(outputs: list[AgentOutput], expected_path: str) -> dict:
    """에이전트 출력과 골든 라벨 비교 → 채점 결과 dict 반환."""
    expected = json.loads(Path(expected_path).read_text(encoding="utf-8"))

    # ── 기대 이슈 멀티셋 ────────────────────────────
    exp_counters: dict[str, Counter] = {}
    for agent_key in _AGENT_KEYS:
        counter: Counter = Counter()
        for exp in expected.get(agent_key, {}).get("expected_issues", []):
            key = (exp["rule_id"], exp.get("file", "(전체)"))
            counter[key] += 1
        exp_counters[agent_key] = counter

    # ── 실제 출력 멀티셋 ────────────────────────────
    out_counters: dict[str, Counter] = {}
    total_output = 0
    for output in outputs:
        counter = out_counters.setdefault(output.agent, Counter())
        for issue in output.issues:
            counter[(issue.rule_id, issue.file)] += 1
            total_output += 1

    # ── 매칭 계산 ────────────────────────────────────
    total_expected = 0
    total_matched = 0
    for agent_key in _AGENT_KEYS:
        exp_c = exp_counters.get(agent_key, Counter())
        out_c = out_counters.get(agent_key, Counter())
        for key, exp_count in exp_c.items():
            total_expected += exp_count
            total_matched += min(exp_count, out_c.get(key, 0))

    recall = total_matched / total_expected if total_expected > 0 else 1.0
    false_alarm = (
        (total_output - total_matched) / total_output if total_output > 0 else 0.0
    )
    passed = recall >= _RECALL_PASS_THRESHOLD and false_alarm <= FALSE_ALARM_THRESHOLD

    return {
        "recall": round(recall, 4),
        "false_alarm": round(false_alarm, 4),
        "total_expected": total_expected,
        "total_output": total_output,
        "total_matched": total_matched,
        "pass": passed,
    }


# ─────────────────────────────────────────────────────────────────────────────
# SESSION 8B — rule별 Precision / Recall / F1 채점기 (다건·양성+음성)
# ─────────────────────────────────────────────────────────────────────────────

def _flatten_expected(expected: dict) -> Counter:
    """expected_output.json → (rule_id, file) 멀티셋."""
    c: Counter = Counter()
    for agent_key in _AGENT_KEYS:
        for exp in expected.get(agent_key, {}).get("expected_issues", []):
            c[(exp["rule_id"], exp.get("file", "(전체)"))] += 1
    return c


def _flatten_output(outputs: list[AgentOutput]) -> Counter:
    """AgentOutput 목록 → (rule_id, file) 멀티셋."""
    c: Counter = Counter()
    for output in outputs:
        for issue in output.issues:
            c[(issue.rule_id, issue.file)] += 1
    return c


def _prf(tp: int, fp: int, fn: int) -> dict:
    """tp/fp/fn → precision·recall·f1(조화평균). 분모 0 이면 0.0(정직)."""
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def evaluate_prf(
    cases: list[dict],
    *,
    overall_f1_pass: float | None = None,
    rule_f1_min: float | None = None,
) -> dict:
    """다건 케이스(양성+음성)를 rule별 + 전체 Precision/Recall/F1 로 채점.

    Args:
        cases: [{"name": str, "outputs": list[AgentOutput], "expected": dict}, ...]
        overall_f1_pass: 전체 F1 합격선(None → settings 기본)
        rule_f1_min: rule별 F1 최소선(None → settings 기본)

    매칭: 기존 evaluate() 와 동일한 (rule_id, file) 멀티셋, 케이스 안에서만 매칭.
    음성 케이스(expected 0)에서 output 이 나오면 그 rule 의 FP 로 잡혀 precision 하락.
    """
    agg: dict[str, dict[str, int]] = {}
    fp_list: list[dict] = []
    fn_list: list[dict] = []
    n_positive = 0
    n_negative = 0

    for case in cases:
        name = case.get("name", "?")
        exp = _flatten_expected(case["expected"])
        out = _flatten_output(case["outputs"])

        if sum(exp.values()) > 0:
            n_positive += 1
        else:
            n_negative += 1

        for rule_id, file in set(exp) | set(out):
            e = exp.get((rule_id, file), 0)
            o = out.get((rule_id, file), 0)
            matched = min(e, o)
            fp = o - matched
            fn = e - matched

            bucket = agg.setdefault(rule_id, {"tp": 0, "fp": 0, "fn": 0})
            bucket["tp"] += matched
            bucket["fp"] += fp
            bucket["fn"] += fn

            for _ in range(fp):
                fp_list.append({"case": name, "rule_id": rule_id, "file": file})
            for _ in range(fn):
                fn_list.append({"case": name, "rule_id": rule_id, "file": file})

    per_rule: dict[str, dict] = {}
    tot_tp = tot_fp = tot_fn = 0
    for rule_id, c in sorted(agg.items()):
        per_rule[rule_id] = _prf(c["tp"], c["fp"], c["fn"])
        tot_tp += c["tp"]
        tot_fp += c["fp"]
        tot_fn += c["fn"]

    overall = _prf(tot_tp, tot_fp, tot_fn)

    if overall_f1_pass is None:
        overall_f1_pass = OVERALL_F1_PASS_THRESHOLD
    if rule_f1_min is None:
        rule_f1_min = RULE_F1_MIN_THRESHOLD

    passed = overall["f1"] >= overall_f1_pass and all(
        r["f1"] >= rule_f1_min for r in per_rule.values()
    )

    return {
        "per_rule": per_rule,
        "overall": overall,
        "fp_list": fp_list,
        "fn_list": fn_list,
        "n_cases": len(cases),
        "n_positive": n_positive,
        "n_negative": n_negative,
        "pass": passed,
    }


# ─────────────────────────────────────────────────────────────────────────────
# __main__: demo_output.json 로드 후 채점
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from pathlib import Path as P

    demo_path = P("demo_output.json")
    expected_path = P("tests/fixtures/expected_output.json")

    if not demo_path.exists():
        print("demo_output.json 없음 — 먼저 py main.py 실행")
        raise SystemExit(1)

    raw = json.loads(demo_path.read_text(encoding="utf-8"))
    from contracts import AgentOutput as AO
    agent_outputs = [AO(**item) for item in raw]

    result = evaluate(agent_outputs, str(expected_path))

    print(f"recall      = {result['recall']:.4f}")
    print(f"false_alarm = {result['false_alarm']:.4f}")
    print(f"matched     = {result['total_matched']} / {result['total_expected']} expected")
    print(f"output      = {result['total_output']} issues")
    status = "PASS" if result["pass"] else "FAIL"
    print(f"status      = {status}")

    if not result["pass"]:
        raise SystemExit(1)
