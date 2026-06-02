"""Dev3 파이프라인 — 골든 4 탐지기 오케스트레이션.

run(dev3_input, repo_path) → list[AgentOutput]

탐지 순서:
  1. coverage.measure()          (test_verification 선행)
  2. missing_funcs.detect()      (coverage.json 의존)
  3. nplus1.detect()             (병렬 실행 대상)
  4. complexity.detect()         (병렬 실행 대상)

부분 실패 허용: 탐지기가 예외를 던지면 빈 결과로 대체 (PRD §3 원칙 ②).
"""
from __future__ import annotations

import time

from assemble.output import assemble_output
from contracts import AgentOutput, Dev3Input
from filter.diff_filter import filter_issues, parse_diff
from harness import instrument
from performance import complexity, nplus1
from test_verification import coverage, missing_funcs


@instrument("dev3.run", "chain")
def run(dev3_input: Dev3Input, repo_path: str) -> list[AgentOutput]:
    """골든 4 탐지기 실행 후 diff 필터 적용 → 2개 AgentOutput 반환."""
    t0 = time.time()

    changed = parse_diff(dev3_input.pr_diff)

    # ── test_verification 탐지기 ──────────────────
    try:
        cov_issues, metrics = coverage.measure(repo_path)
    except Exception:
        cov_issues, metrics = [], None

    try:
        mf_issues = missing_funcs.detect(repo_path, changed)
    except Exception:
        mf_issues = []

    # ── performance 탐지기 ───────────────────────
    try:
        n1_issues = nplus1.detect(repo_path, changed)
    except Exception:
        n1_issues = []

    try:
        cx_issues = complexity.detect(repo_path, changed)
    except Exception:
        cx_issues = []

    elapsed_ms = int((time.time() - t0) * 1000)

    # ── diff 교집합 필터 ─────────────────────────
    test_issues = filter_issues(cov_issues + mf_issues, changed, repo_path)
    perf_issues = filter_issues(n1_issues + cx_issues, changed, repo_path)

    # ── 조립 ────────────────────────────────────
    tv_output = assemble_output(
        task_id=dev3_input.task_id,
        scan_id=dev3_input.scan_id,
        pr_id=dev3_input.pr_id,
        agent="test_verification",
        issues=test_issues,
        metrics=metrics,
        execution_ms=elapsed_ms,
    )
    perf_output = assemble_output(
        task_id=dev3_input.task_id,
        scan_id=dev3_input.scan_id,
        pr_id=dev3_input.pr_id,
        agent="performance",
        issues=perf_issues,
        metrics=None,
        execution_ms=elapsed_ms,
    )

    return [tv_output, perf_output]


# ─────────────────────────────────────────────────────────────────────────────
# __main__: fixture 입력으로 실행 후 demo_output.json 저장
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json
    from pathlib import Path

    from contracts import Developer, RepoInfo

    repo_path = str(Path("tests/fixtures/sample_repo").resolve())
    pr_diff = Path("tests/fixtures/sample_pr.diff").read_text(encoding="utf-8")

    inp = Dev3Input(
        task_id="demo-task-001",
        scan_id=1,
        pr_id="PR-demo",
        pr_diff=pr_diff,
        repo=RepoInfo(clone_url="https://github.com/example/repo", commit_sha="abc123"),
        developer=Developer(id="junior_dev_01"),
    )

    outputs = run(inp, repo_path)

    total_issues = sum(len(o.issues) for o in outputs)
    print(f"이슈 탐지: {total_issues}건")
    for o in outputs:
        print(f"  [{o.agent}] major={o.summary.major} minor={o.summary.minor}")
        for i in o.issues:
            loc = f"{i.file}:{i.line}" if i.line else i.file
            print(f"    [{i.severity}] {i.rule_id}  {loc}  {i.message[:50]}")

    output_data = [o.model_dump() for o in outputs]
    Path("demo_output.json").write_text(
        json.dumps(output_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\ndemo_output.json 저장 완료")
