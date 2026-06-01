"""Task 7 — 시간복잡도 탐지기 TDD 테스트.

depth 2 → Minor (O(n²))
depth 3 → Major (O(n³))
comprehension → 단일 루프로 간주 (0)
"""
import textwrap

import pytest

from performance.complexity import detect


# ────────────────────────────────────────────
# Helper
# ────────────────────────────────────────────

def _write_and_detect(tmp_path, code: str):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "f.py").write_text(textwrap.dedent(code), encoding="utf-8")
    changed = {"src/f.py": set(range(1, 100))}
    return detect(str(tmp_path), changed)


# ════════════════════════════════════════════
# 부정 케이스 — 이슈 없어야 함 (4)
# ════════════════════════════════════════════

def test_no_loops_zero_issues(tmp_path):
    """루프 없음 → 0."""
    issues = _write_and_detect(tmp_path, """
        def foo(x):
            return x + 1
    """)
    assert len(issues) == 0


def test_single_loop_zero_issues(tmp_path):
    """단일 루프 → 0 (O(n))."""
    issues = _write_and_detect(tmp_path, """
        def foo(xs):
            for x in xs:
                print(x)
    """)
    assert len(issues) == 0


def test_adjacent_loops_zero_issues(tmp_path):
    """비중첩 인접 루프 2개 → 0 (중첩 아님)."""
    issues = _write_and_detect(tmp_path, """
        def foo(xs, ys):
            for x in xs:
                print(x)
            for y in ys:
                print(y)
    """)
    assert len(issues) == 0


def test_list_comprehension_zero_issues(tmp_path):
    """list comprehension → 단일 루프로 간주 → 0."""
    issues = _write_and_detect(tmp_path, """
        def foo(xs):
            return [x * 2 for x in xs]
    """)
    assert len(issues) == 0


# ════════════════════════════════════════════
# 긍정 케이스 — 이슈 있어야 함 (2)
# ════════════════════════════════════════════

def test_double_nested_loop_minor(tmp_path):
    """이중 중첩 → PERF-001 Minor 1건 (O(n²))."""
    issues = _write_and_detect(tmp_path, """
        def foo(xs, ys):
            for x in xs:
                for y in ys:
                    print(x, y)
    """)
    assert len(issues) == 1
    assert issues[0].severity == "Minor"
    assert issues[0].rule_id == "PERF-001"


def test_triple_nested_loop_major(tmp_path):
    """삼중 중첩 → PERF-001 Major 1건 (O(n³))."""
    issues = _write_and_detect(tmp_path, """
        def foo(xs, ys, zs):
            for x in xs:
                for y in ys:
                    for z in zs:
                        print(x, y, z)
    """)
    assert len(issues) == 1
    assert issues[0].severity == "Major"
    assert issues[0].rule_id == "PERF-001"
