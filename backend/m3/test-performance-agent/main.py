"""Dev3 파이프라인 — 탐지기 6개 오케스트레이션.

run(dev3_input, repo_path) → list[AgentOutput]

탐지 순서:
  1. coverage.measure()          (test_verification 선행)
  2. missing_funcs.detect()      (coverage.json 의존)
  3. edge_cases.detect()         (TEST-003; LLM 키 없으면 휴리스틱 폴백)
  4. nplus1.detect()             (병렬 실행 대상)
  5. complexity.detect()         (병렬 실행 대상)
  6. memory_leak.detect()        (PERF-003; LLM 키 없으면 휴리스틱 폴백)

부분 실패 허용: 탐지기가 예외를 던지면 빈 결과로 대체 (PRD §3 원칙 ②).

결정성: LLM 키 있으면 LLM 모드(비결정적), 없으면 휴리스틱(결정적).
CI/데모에서는 GOOGLE_API_KEY 없이 실행해 결정성 보장 권장.(b) 선택
"""
from __future__ import annotations

import os
import time

from assemble.output import assemble_output
from contracts import AgentOutput, Dev3Input
from enrich import code_context, framework
from filter.diff_filter import filter_issues, parse_diff
from harness import instrument
from performance import complexity, memory_leak, nplus1
from rag import augment as rag_augment
from test_verification import coverage, edge_cases, missing_funcs


@instrument("dev3.run", "chain")
def run(dev3_input: Dev3Input, repo_path: str) -> list[AgentOutput]:
    """탐지기 6개 실행 후 diff 필터 적용 → 2개 AgentOutput 반환."""
    t0 = time.time()

    changed = parse_diff(dev3_input.pr_diff)

    # ── test_verification 탐지기 ──────────────────
    try:
        cov_issues, metrics = coverage.measure(repo_path, changed)
    except Exception:
        cov_issues, metrics = [], None

    try:
        mf_issues = missing_funcs.detect(repo_path, changed)
    except Exception:
        mf_issues = []

    try:
        ec_issues = edge_cases.detect(repo_path, changed)
    except Exception:
        ec_issues = []

    # ── performance 탐지기 ───────────────────────
    try:
        n1_issues = nplus1.detect(repo_path, changed)
    except Exception:
        n1_issues = []

    try:
        cx_issues = complexity.detect(repo_path, changed)
    except Exception:
        cx_issues = []

    try:
        ml_issues = memory_leak.detect(repo_path, changed)
    except Exception:
        ml_issues = []

    elapsed_ms = int((time.time() - t0) * 1000)

    # ── diff 교집합 필터 ─────────────────────────
    test_issues = filter_issues(cov_issues + mf_issues + ec_issues, changed, repo_path)
    perf_issues = filter_issues(n1_issues + cx_issues + ml_issues, changed, repo_path)

    # ── code_snippet·name_of_function(AST=사실) — test·perf 모두. code_context(LLM)은 perf만 ──
    code_context.augment_issues(test_issues, repo_path, with_llm=False)
    code_context.augment_issues(perf_issues, repo_path)

    # ── programming_language·framework·framework_version 채움 (레포 단위, 모든 이슈) ──
    framework.augment_issues(test_issues + perf_issues, repo_path)

    # ── github_id 채움 — PR 작성자 GitHub 아이디(문자), 모든 이슈 ──
    github_id = dev3_input.developer.id
    for issue in test_issues + perf_issues:
        issue.github_id = github_id

    # ── 사내 컨벤션 RAG 채움 (rag_context) — RAG_ENABLED 이면 실행 ──
    # 기본 ON: docker-compose 에서 RAG_ENABLED=1 설정 → 실 분석 시 rag_context 채움.
    # 단위테스트: conftest _rag_off autouse 가 unset → BGE-M3·GCP 비접촉.
    if os.getenv("RAG_ENABLED"):
        rag_augment.augment_issues(test_issues)
        rag_augment.augment_issues(perf_issues)

    # ── performance metrics — 복잡도 이슈의 중첩 깊이 중 최댓값(있을 때만) ──
    # depth 실린 이슈만 집계 → 복잡도 이슈 0건이면 None 유지(가짜 숫자 금지).
    # 코멘트 렌더(_review_metrics→_metrics_line)가 max_complexity 키를 읽어 '최대 복잡도 N'으로 출력.
    cx_depths = [i.complexity_depth for i in perf_issues if i.complexity_depth is not None]
    perf_metrics = {"max_complexity": max(cx_depths)} if cx_depths else None

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
        metrics=perf_metrics,
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
