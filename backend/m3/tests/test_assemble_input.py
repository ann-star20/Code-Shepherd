"""⓪ assemble_input 단위테스트 — 계약 기준(contracts/README.md 표 ⓪) + §9.4 입력 다이어트.

브리프 기준: "샘플 payload → 스키마 검증 통과".
추가 기준(D2 선반영 지시): 변경 줄을 포함하는 함수 전문만 컨텍스트로 추출 (파일 전문 금지).
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.nodes.assemble_input import _changed_lines_by_file, assemble_input

SAMPLE_PY = textwrap.dedent("""\
    import os


    def other_fn():
        return 1


    def target_fn(a, b):
        x = a + b
        y = x * 2
        return y
""")

DIFF_ONE_LINE_IN_TARGET = textwrap.dedent("""\
    diff --git a/src/sample.py b/src/sample.py
    --- a/src/sample.py
    +++ b/src/sample.py
    @@ -7,4 +7,5 @@

     def target_fn(a, b):
         x = a + b
    +    y = x * 2
         return y
""")


def _files_root(tmp_path: Path) -> str:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "sample.py").write_text(SAMPLE_PY, encoding="utf-8")
    return str(tmp_path)


def test_sample_payload_passes_schema_and_includes_diff():
    out = assemble_input({"diff": DIFF_ONE_LINE_IN_TARGET, "file_paths": ["src/sample.py"], "repo_meta": {}})
    assert "pr_context" in out
    assert DIFF_ONE_LINE_IN_TARGET.strip() in out["pr_context"]


def test_invalid_payload_rejected():
    with pytest.raises(ValidationError):
        assemble_input({"file_paths": ["x.py"], "repo_meta": {}})  # diff 누락


def test_changed_lines_parser():
    changed = _changed_lines_by_file(DIFF_ONE_LINE_IN_TARGET)
    assert changed == {"src/sample.py": {10}}


def test_function_context_extracted_only_for_changed_function(tmp_path):
    root = _files_root(tmp_path)
    out = assemble_input({
        "diff": DIFF_ONE_LINE_IN_TARGET,
        "file_paths": ["src/sample.py"],
        "repo_meta": {"files_root": root},
    })
    ctx = out["pr_context"]
    assert "def target_fn(a, b):" in ctx          # 변경 줄 포함 함수는 전문 포함
    assert "def other_fn" not in ctx              # 변경 없는 함수는 제외 (입력 다이어트)


def test_module_level_change_has_no_function_context(tmp_path):
    root = _files_root(tmp_path)
    diff = textwrap.dedent("""\
        diff --git a/src/sample.py b/src/sample.py
        --- a/src/sample.py
        +++ b/src/sample.py
        @@ -1,1 +1,2 @@
         import os
        +import sys
    """)
    out = assemble_input({"diff": diff, "file_paths": ["src/sample.py"], "repo_meta": {"files_root": root}})
    assert "함수 컨텍스트" not in out["pr_context"]   # 함수 밖 변경 → 컨텍스트 섹션 없음


def test_without_files_root_returns_diff_only():
    out = assemble_input({"diff": DIFF_ONE_LINE_IN_TARGET, "file_paths": ["src/sample.py"], "repo_meta": {}})
    assert "함수 컨텍스트" not in out["pr_context"]


def test_same_function_changed_twice_included_once(tmp_path):
    root = _files_root(tmp_path)
    diff = textwrap.dedent("""\
        diff --git a/src/sample.py b/src/sample.py
        --- a/src/sample.py
        +++ b/src/sample.py
        @@ -8,3 +8,5 @@
         def target_fn(a, b):
             x = a + b
        +    y = x * 2
        +    z = y + 1
             return y
    """)
    out = assemble_input({"diff": diff, "file_paths": ["src/sample.py"], "repo_meta": {"files_root": root}})
    # 같은 함수 안에서 2줄이 바뀌어도 함수 컨텍스트 섹션에는 함수 전문이 1회만
    section = out["pr_context"].split("## 변경 함수 컨텍스트")[1]
    assert section.count("def target_fn(a, b):") == 1
