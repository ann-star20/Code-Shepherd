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

from config.settings import FALSE_ALARM_THRESHOLD  # noqa: E402
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
