"""diff 교집합 필터 (PRD §3 원칙 ③, §7.3).

parse_diff  : unified diff → {rel_path: set[new_line_numbers]}
filter_issues: 이슈 목록 × changed → 신입이 바꾼 함수 범위만 통과

필터 규칙 (PRD §7.3 flowchart):
1. file == "(전체)" 또는 line is None  → 무조건 유지
2. file이 diff에 없음                  → drop
3. line이 diff 직접 줄 또는 1-hop 함수 범위 안 → 유지, 아니면 drop
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from contracts import Issue


# ──────────────────────────────────────────
# parse_diff
# ──────────────────────────────────────────

def parse_diff(pr_diff: str) -> dict[str, set[int]]:
    """Unified diff 파싱 → 신규 파일별 추가된 줄 번호 집합 반환."""
    changed: dict[str, set[int]] = {}
    current_file: str | None = None
    new_line = 0

    for raw in pr_diff.splitlines():
        # 새 파일 대상 (b/path)
        if raw.startswith("+++ b/"):
            current_file = raw[6:]
            changed.setdefault(current_file, set())
            new_line = 0
        elif raw.startswith("+++ "):
            current_file = None  # /dev/null 등 삭제 파일
        # 헝크 헤더 @@ -old +new @@
        elif raw.startswith("@@ ") and current_file is not None:
            m = re.match(r"@@ -\S+ \+(\d+)", raw)
            if m:
                new_line = int(m.group(1))
        # 추가된 줄 (+, +++ 헤더 제외)
        elif (
            current_file is not None
            and raw.startswith("+")
            and not raw.startswith("+++")
        ):
            changed[current_file].add(new_line)
            new_line += 1
        # 삭제된 줄 (-, --- 헤더 제외) — new_line 불변
        elif (
            current_file is not None
            and raw.startswith("-")
            and not raw.startswith("---")
        ):
            pass
        # 컨텍스트 줄 (공백 시작)
        elif current_file is not None and raw.startswith(" "):
            new_line += 1

    return changed


# ──────────────────────────────────────────
# 1-hop 함수 범위 확장
# ──────────────────────────────────────────

def _function_ranges(source: str) -> list[tuple[int, int]]:
    """AST로 파일 내 모든 함수의 (start_line, end_line) 목록 반환."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    return [
        (node.lineno, node.end_lineno or node.lineno)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _expand_1hop(repo_path: str, changed: dict[str, set[int]]) -> dict[str, set[int]]:
    """changed 줄이 속한 함수 전체를 포함하도록 확장."""
    expanded: dict[str, set[int]] = {f: set(lines) for f, lines in changed.items()}
    repo = Path(repo_path)

    for rel_path, lines in changed.items():
        if not rel_path.endswith(".py"):
            continue
        src_file = repo / rel_path
        if not src_file.exists():
            continue
        try:
            source = src_file.read_text(encoding="utf-8")
        except OSError:
            continue

        for start, end in _function_ranges(source):
            func_lines = set(range(start, end + 1))
            if func_lines & lines:  # 함수 안에 changed 줄이 있으면 전체 함수 포함
                expanded[rel_path] |= func_lines

    return expanded


# ──────────────────────────────────────────
# filter_issues
# ──────────────────────────────────────────

def filter_issues(
    issues: list[Issue],
    changed: dict[str, set[int]],
    repo_path: str,
) -> list[Issue]:
    """PRD §7.3 필터 규칙 적용.

    1. file == '(전체)' 또는 line is None → 유지
    2. file이 diff에 없음 → drop
    3. line이 1-hop 확장 범위 안 → 유지, 아니면 drop
    """
    # 경로 구분자 정규화 (Windows \\ → /)
    norm_changed = {k.replace("\\", "/"): v for k, v in changed.items()}
    expanded = _expand_1hop(repo_path, norm_changed)

    result: list[Issue] = []
    for issue in issues:
        if issue.file == "(전체)" or issue.line is None:
            result.append(issue)
            continue

        norm_file = issue.file.replace("\\", "/")
        if norm_file not in expanded:
            continue  # drop: diff 밖 파일

        if issue.line in expanded[norm_file]:
            result.append(issue)
        # else: drop

    return result
