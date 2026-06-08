"""Task 6 — N+1 탐지기 TDD 테스트.

긍정 케이스 (잡아야 함): 3개
부정 케이스 (잡으면 안 됨): 8개  ← 긍정보다 많아야 함 (PRD §5.4)
"""
import textwrap

import pytest

from performance.nplus1 import detect


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
# 긍정 케이스 (3)
# ════════════════════════════════════════════

def test_for_loop_query_one_issue(tmp_path):
    """for 루프 안 .query() → PERF-002 Major 1건."""
    issues = _write_and_detect(tmp_path, """
        items = [1, 2, 3]
        for item in items:
            db.query(item)
    """)
    assert len(issues) == 1
    assert issues[0].severity == "Major"
    assert issues[0].rule_id == "PERF-002"


def test_while_loop_execute_one_issue(tmp_path):
    """while 루프 안 .execute() → 1건."""
    issues = _write_and_detect(tmp_path, """
        while True:
            db.execute("SELECT 1")
            break
    """)
    assert len(issues) == 1
    assert issues[0].severity == "Major"


def test_nested_loop_filter_one_issue(tmp_path):
    """중첩 루프 + 내부 .filter() → 중복 없이 정확히 1건."""
    issues = _write_and_detect(tmp_path, """
        for x in xs:
            for y in ys:
                session.filter(y)
    """)
    assert len(issues) == 1


# ════════════════════════════════════════════
# 부정 케이스 (8) — 잡으면 안 됨
# ════════════════════════════════════════════

def test_loop_get_no_issue(tmp_path):
    """루프 안 .get() → 0 (DB_CALL_NAMES 제외)."""
    issues = _write_and_detect(tmp_path, """
        for item in items:
            obj.get(item)
    """)
    assert len(issues) == 0


def test_loop_all_no_issue(tmp_path):
    """루프 안 .all() → 0 (DB_CALL_NAMES 제외)."""
    issues = _write_and_detect(tmp_path, """
        for item in items:
            obj.all()
    """)
    assert len(issues) == 0


def test_loop_first_no_issue(tmp_path):
    """루프 안 .first() → 0 (DB_CALL_NAMES 제외)."""
    issues = _write_and_detect(tmp_path, """
        for item in items:
            obj.first()
    """)
    assert len(issues) == 0


def test_loop_count_no_issue(tmp_path):
    """루프 안 .count() → 0 (DB_CALL_NAMES 제외)."""
    issues = _write_and_detect(tmp_path, """
        for item in items:
            qs.count()
    """)
    assert len(issues) == 0


def test_query_outside_loop_no_issue(tmp_path):
    """루프 밖 단일 .query() → 0."""
    issues = _write_and_detect(tmp_path, """
        db.query("SELECT 1")
    """)
    assert len(issues) == 0


def test_self_query_no_issue(tmp_path):
    """`self.query()` 자기참조 → 0 (클래스 내부 메서드 오탐 방지)."""
    issues = _write_and_detect(tmp_path, """
        class Repo:
            def query(self, x):
                return x
            def method(self):
                for item in items:
                    self.query(item)
    """)
    assert len(issues) == 0


def test_loop_arithmetic_no_issue(tmp_path):
    """루프 안 산술만 → 0."""
    issues = _write_and_detect(tmp_path, """
        for i in range(10):
            x = i * 2 + 1
    """)
    assert len(issues) == 0


def test_icecream_like_no_issue(tmp_path):
    """icecream 같은 비-DB 라이브러리 사용 → 0 (메서드명 충돌 없음)."""
    issues = _write_and_detect(tmp_path, """
        from icecream import ic
        for item in items:
            ic(item)
            val = item.get("key", None)
    """)
    assert len(issues) == 0
