"""시간복잡도 탐지 — 중첩 루프 깊이 분석 (PERF-001).

depth 2 → Minor (O(n²))
depth 3+ → Major (O(n³)+)
comprehension은 단일 루프로 간주 → 중첩 깊이에 불포함 (PRD §5.4)
"""
from __future__ import annotations

import ast
from pathlib import Path

from config.conventions import complexity_rules
from contracts import Issue
from harness import instrument

_COMP_TYPES = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def _max_loop_depth(node: ast.AST) -> int:
    """Return the maximum for/while nesting depth within this subtree.

    Comprehensions are treated as single-loop units (depth 0 contribution to
    outer nesting) so that [x for x in xs] counts as depth 1 by itself but
    does not add to the depth of an enclosing loop.
    Nested functions are independent scopes — their loops don't count.
    """
    if isinstance(node, _COMP_TYPES):
        return 0  # comprehension = isolated single-loop unit
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        return 0  # nested scope — independent

    is_loop = isinstance(node, (ast.For, ast.While))
    child_max = max(
        (_max_loop_depth(child) for child in ast.iter_child_nodes(node)),
        default=0,
    )
    return (1 + child_max) if is_loop else child_max


def _top_level_loops(node: ast.AST):
    """Yield outermost For/While nodes (not nested inside another loop).

    Recurses into functions/classes but stops at the first loop it encounters
    (doesn't descend into loop bodies for top-level search purposes).
    Comprehensions are transparent (skipped entirely).
    """
    if isinstance(node, (ast.For, ast.While)):
        yield node
        return  # don't look for nested loops — depth is handled by _max_loop_depth
    if isinstance(node, _COMP_TYPES):
        return  # comprehensions have no sub-loops for nesting analysis
    for child in ast.iter_child_nodes(node):
        yield from _top_level_loops(child)


def _detect_in_source(source: str, rel_path: str) -> list[Issue]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    # 기준값 정본: DB(convention_policies) → 없으면 하드코딩 fallback.
    rules = complexity_rules()
    major_depth = rules["major_depth"]
    minor_depth = rules["minor_depth"]

    issues: list[Issue] = []
    for loop_node in _top_level_loops(tree):
        depth = _max_loop_depth(loop_node)
        if depth >= major_depth:
            issues.append(
                Issue(
                    severity="Major",
                    file=rel_path,
                    line=loop_node.lineno,
                    message=(
                        f"O(n^{depth}) 이상의 시간복잡도: "
                        f"{depth}중 중첩 루프가 감지되었습니다."
                    ),
                    rule_id="PERF-001",
                    suggestion="루프를 평탄화하거나 적절한 자료구조로 복잡도를 낮추세요.",
                    keyword="시간복잡도",
                    sub_category="Nested Loop",
                )
            )
        elif depth >= minor_depth:
            issues.append(
                Issue(
                    severity="Minor",
                    file=rel_path,
                    line=loop_node.lineno,
                    message=(
                        f"O(n^{depth}) 시간복잡도: "
                        f"{depth}중 중첩 루프가 감지되었습니다."
                    ),
                    rule_id="PERF-001",
                    suggestion="루프를 평탄화하거나 적절한 자료구조로 복잡도를 낮추세요.",
                    keyword="시간복잡도",
                    sub_category="Nested Loop",
                )
            )
    return issues


@instrument("complexity")
def detect(repo_path: str, changed: dict[str, set[int]]) -> list[Issue]:
    """Detect complexity issues in changed Python files."""
    issues: list[Issue] = []
    repo = Path(repo_path)

    for rel_path in changed:
        if not rel_path.endswith(".py"):
            continue
        filepath = repo / rel_path
        if not filepath.exists():
            continue
        try:
            source = filepath.read_text(encoding="utf-8")
        except OSError:
            continue
        issues.extend(_detect_in_source(source, rel_path.replace("\\", "/")))

    return issues
