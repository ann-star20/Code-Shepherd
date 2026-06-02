"""테스트 커버리지 분석 — coverage.json 파싱 + 메트릭 3종 산출 + TEST-001 이슈.

반환: (list[Issue], dict | None)
- coverage.json 없거나 num_statements=0 → ([], None)  ← 정직성 원칙
- branch 데이터 없으면 coverage_branch 키 자체를 제외 (null 금지)
- func 커버리지: AST body-line 체크 — def-line 함정 방지
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Optional

from config.settings import COVERAGE_THRESHOLD
from contracts import Issue
from harness import instrument


@instrument("coverage")
def measure(repo_path: str) -> tuple[list[Issue], Optional[dict]]:
    """coverage.json을 읽어 메트릭 산출 및 이슈 생성."""
    cov_path = Path(repo_path) / "coverage.json"
    if not cov_path.exists():
        return [], None

    data = json.loads(cov_path.read_text(encoding="utf-8"))
    totals = data.get("totals", {})
    num_statements = totals.get("num_statements", 0)

    if num_statements == 0:
        return [], None

    metrics: dict = {}
    issues: list[Issue] = []

    # 라인 커버리지
    line_pct = totals.get("percent_covered", 0.0) / 100.0
    metrics["coverage_line"] = round(line_pct, 4)

    if line_pct < COVERAGE_THRESHOLD:
        issues.append(
            Issue(
                severity="Major",
                file="(전체)",
                line=None,
                message=(
                    f"테스트 라인 커버리지 {line_pct * 100:.1f}%"
                    f" < 기준 {COVERAGE_THRESHOLD * 100:.0f}%."
                ),
                rule_id="TEST-001",
                suggestion="테스트를 추가해 커버리지를 80% 이상으로 올리세요.",
                keyword="커버리지 미충족",
                sub_keyword="(전체)",
                metric_value=f"{line_pct * 100:.1f}%",
            )
        )

    # 브랜치 커버리지 — 데이터가 있을 때만 키 추가 (없으면 키 자체 제외)
    meta = data.get("meta", {})
    if meta.get("branch_coverage", False):
        num_branches = totals.get("num_branches", 0)
        if num_branches > 0:
            covered_branches = totals.get("covered_branches", 0)
            metrics["coverage_branch"] = round(covered_branches / num_branches, 4)

    # 함수 커버리지 — AST body-line 체크 (def-line 함정 방지)
    func_cov = _calc_func_coverage(repo_path, data)
    if func_cov is not None:
        metrics["coverage_func"] = round(func_cov, 4)

    return issues, metrics


def _calc_func_coverage(repo_path: str, cov_data: dict) -> Optional[float]:
    """AST로 함수별 본문 커버리지 계산.

    def 줄은 모듈 import 시 항상 실행되므로 제외하고,
    body[0].lineno ~ end_lineno 범위와 executed_lines 교집합으로 판정.
    """
    total_funcs = 0
    covered_funcs = 0

    for rel_path_str, file_data in cov_data.get("files", {}).items():
        executed_lines = set(file_data.get("executed_lines", []))
        # Windows / Unix 경로 정규화
        norm_rel = rel_path_str.replace("\\", "/")
        src_path = Path(repo_path) / Path(norm_rel)
        if not src_path.exists():
            continue

        try:
            source = src_path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (SyntaxError, OSError):
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.body:
                continue

            total_funcs += 1
            body_start = node.body[0].lineno
            body_end = node.end_lineno or body_start
            body_lines = set(range(body_start, body_end + 1))

            if body_lines & executed_lines:
                covered_funcs += 1

    if total_funcs == 0:
        return None
    return covered_funcs / total_funcs
