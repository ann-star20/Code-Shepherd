"""N+1 쿼리 탐지 — 루프 본문 내 DB 호출 패턴 (PERF-002).

DB_CALL_NAMES: query/execute/filter/fetchone/fetchall/scalar (좁은 집합 — PRD §5.4/§18)
제외: .get/.all/.first/.count (일반 메서드 이름과 충돌)
제외: self.method() (자기참조 — 클래스 내부 메서드 오탐 방지)
"""
from __future__ import annotations

import ast
from pathlib import Path

from config.settings import DB_CALL_NAMES
from contracts import Issue
from harness import instrument


def _is_db_call(node: ast.Call) -> bool:
    """Attribute call on a non-self object using a DB_CALL_NAMES method."""
    if not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr not in DB_CALL_NAMES:
        return False
    # Exclude self.method() — self-reference (test-class helpers, etc.)
    if isinstance(node.func.value, ast.Name) and node.func.value.id == "self":
        return False
    return True


def _detect_in_source(source: str, rel_path: str) -> list[Issue]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    issues: list[Issue] = []
    seen_lines: set[int] = set()

    for node in ast.walk(tree):
        if not isinstance(node, (ast.For, ast.While)):
            continue
        # Walk the entire loop subtree; deduplicate by line to avoid double-reporting
        # when the same DB call is inside nested loops.
        for child in ast.walk(node):
            if isinstance(child, ast.Call) and _is_db_call(child):
                if child.lineno not in seen_lines:
                    seen_lines.add(child.lineno)
                    issues.append(
                        Issue(
                            severity="Major",
                            file=rel_path,
                            line=child.lineno,
                            message="N+1 쿼리: 루프 안에서 DB 호출이 반복됩니다.",
                            rule_id="PERF-002",
                            suggestion=(
                                "joinedload()/selectinload() 등으로 루프 밖에서 조회하세요."
                            ),
                            keyword="N+1 쿼리",
                            sub_category="Database/API Loop Call",
                        )
                    )
    return issues


@instrument("nplus1")
def detect(repo_path: str, changed: dict[str, set[int]]) -> list[Issue]:
    """Detect N+1 query patterns in changed Python files."""
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
