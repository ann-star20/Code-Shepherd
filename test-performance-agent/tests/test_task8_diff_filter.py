"""Task 8 — filter/diff_filter TDD 테스트.

긍정 케이스:
  - parse_diff: + 줄만 추출
  - filter: file=="(전체)" / line==None 무조건 유지
  - filter: diff 안 줄 → 유지
  - filter: 1-hop 함수 확장 → 유지
부정 케이스:
  - parse_diff: - 줄 무시
  - filter: diff 밖 파일 → drop
  - filter: diff 밖 다른 함수 줄 → drop
"""
import textwrap

import pytest

from contracts import Issue
from filter.diff_filter import filter_issues, parse_diff


# ══════════════════════════════════════════
# parse_diff
# ══════════════════════════════════════════


def test_parse_diff_added_lines():
    """`+` 줄만 changed에 추가된다."""
    diff = textwrap.dedent("""\
        diff --git a/src/foo.py b/src/foo.py
        new file mode 100644
        --- /dev/null
        +++ b/src/foo.py
        @@ -0,0 +1,3 @@
        +line1
        +line2
        +line3
    """)
    changed = parse_diff(diff)
    assert "src/foo.py" in changed
    assert changed["src/foo.py"] == {1, 2, 3}


def test_parse_diff_minus_lines_not_added():
    """`-` 줄은 changed에 들어가지 않는다."""
    diff = textwrap.dedent("""\
        diff --git a/src/foo.py b/src/foo.py
        --- a/src/foo.py
        +++ b/src/foo.py
        @@ -1,2 +1,1 @@
        -removed_line
         context_line
    """)
    changed = parse_diff(diff)
    assert changed.get("src/foo.py", set()) == set()


# ══════════════════════════════════════════
# filter_issues
# ══════════════════════════════════════════


def test_filter_global_file_issue_always_kept():
    """file == '(전체)' → 무조건 유지."""
    issue = Issue(
        severity="Major", file="(전체)", line=None, message="cov", rule_id="TEST-001"
    )
    result = filter_issues([issue], changed={}, repo_path=".")
    assert result == [issue]


def test_filter_none_line_always_kept():
    """line == None → 무조건 유지 (파일이 diff 밖이어도)."""
    issue = Issue(
        severity="Major", file="src/posts.py", line=None, message="cov", rule_id="TEST-001"
    )
    result = filter_issues([issue], changed={}, repo_path=".")
    assert result == [issue]


def test_filter_outside_diff_dropped():
    """diff에 없는 파일 이슈 → drop."""
    issue = Issue(
        severity="Major",
        file="src/old_utils.py",
        line=7,
        message="N+1",
        rule_id="PERF-002",
    )
    result = filter_issues([issue], changed={"src/posts.py": {1, 2, 3}}, repo_path=".")
    assert result == []


def test_filter_direct_diff_line_kept(tmp_path):
    """diff 안 줄에 정확히 해당하는 이슈 → 유지."""
    src = tmp_path / "src" / "foo.py"
    src.parent.mkdir()
    src.write_text("x = 1\ny = 2\nz = 3\n", encoding="utf-8")

    issue = Issue(
        severity="Minor", file="src/foo.py", line=2, message="...", rule_id="PERF-001"
    )
    result = filter_issues([issue], changed={"src/foo.py": {2}}, repo_path=str(tmp_path))
    assert result == [issue]


def test_filter_1hop_function_range_kept(tmp_path):
    """diff 줄과 같은 함수 안 이슈 → 1-hop 확장으로 유지."""
    src = tmp_path / "src" / "foo.py"
    src.parent.mkdir()
    src.write_text(
        textwrap.dedent("""\
            def foo():
                x = 1
                y = 2
                return x + y
            def bar():
                z = 3
        """),
        encoding="utf-8",
    )
    # changed: line 2 (x=1 in foo) — 이슈는 line 3 (y=2, 같은 함수, diff 미포함)
    issue = Issue(
        severity="Minor", file="src/foo.py", line=3, message="...", rule_id="PERF-001"
    )
    result = filter_issues(
        [issue], changed={"src/foo.py": {2}}, repo_path=str(tmp_path)
    )
    assert result == [issue], "같은 함수 범위 이슈는 1-hop으로 유지해야 함"


def test_filter_different_function_dropped(tmp_path):
    """diff 줄과 다른 함수 안 이슈 → drop."""
    src = tmp_path / "src" / "foo.py"
    src.parent.mkdir()
    src.write_text(
        textwrap.dedent("""\
            def foo():
                x = 1
                y = 2
                return x + y
            def bar():
                z = 3
        """),
        encoding="utf-8",
    )
    # changed: line 2 (x=1 in foo) — 이슈는 line 6 (bar 안, 다른 함수)
    issue = Issue(
        severity="Minor", file="src/foo.py", line=6, message="...", rule_id="PERF-001"
    )
    result = filter_issues(
        [issue], changed={"src/foo.py": {2}}, repo_path=str(tmp_path)
    )
    assert result == [], "다른 함수 이슈는 drop 해야 함"
