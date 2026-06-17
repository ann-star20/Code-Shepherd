"""⓪ assemble_input — diff, file_paths, repo_meta → State.pr_context

계약: contracts/README.md 표 ⓪. LLM 미사용 노드.
pr_context = diff + "변경 줄을 포함하는 함수 전문"만 (§9.4 입력 다이어트 — 파일 전문 금지).

함수 추출은 Code-Shepherd enrich/code_context.py 의 _enclosing_function_source()를
이식한 것 (D1 점검에서 채택 판정된 검증 로직, 정현 승인 D2 선반영).

파일 본문 소스: repo_meta["files_root"] (변경 파일들이 놓인 로컬 디렉토리)
- 하네스: golden/pr_NNN/files, 웹훅(D4): checkout 디렉토리, Streamlit: 생략 가능
- 없거나 파일을 못 읽으면 diff 단독으로 동작 (graceful degradation).
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from contracts import ReviewInput, ReviewState

_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def _changed_lines_by_file(diff: str) -> dict[str, set[int]]:
    """unified diff → {파일경로: 추가/수정된 새 파일 기준 줄번호 집합}."""
    changed: dict[str, set[int]] = {}
    current: str | None = None
    new_lineno = 0
    in_hunk = False

    for line in diff.splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip()
            current = None if path == "/dev/null" else path.removeprefix("b/")
            in_hunk = False
            continue
        m = _HUNK_RE.match(line)
        if m:
            new_lineno = int(m.group(1))
            in_hunk = True
            continue
        if not in_hunk or current is None:
            continue
        if line.startswith("+"):
            changed.setdefault(current, set()).add(new_lineno)
            new_lineno += 1
        elif line.startswith("-") or line.startswith("\\"):
            continue  # 구버전 줄 / "\ No newline" — 새 파일 줄번호 진행 없음
        else:
            new_lineno += 1  # context 줄
    return changed


def _enclosing_function_source(source: str, line: int) -> str:
    """주어진 줄을 포함하는 가장 안쪽 함수의 소스. 없으면 빈 문자열.

    (Code-Shepherd enrich/code_context.py 에서 이식 — AST=사실 원칙)
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ""
    best: tuple[int, int, ast.AST] | None = None
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        start = node.lineno
        end = getattr(node, "end_lineno", start) or start
        if start <= line <= end:
            if best is None or (end - start) < (best[1] - best[0]):
                best = (start, end, node)
    if best is None:
        return ""
    return ast.get_source_segment(source, best[2]) or ""


def _function_contexts(diff: str, files_root: str) -> dict[str, list[str]]:
    """변경 줄을 포함하는 함수 전문을 파일별로 수집 (중복 함수는 1회)."""
    root = Path(files_root)
    contexts: dict[str, list[str]] = {}
    for rel_path, lines in _changed_lines_by_file(diff).items():
        if not rel_path.endswith(".py"):
            continue
        fp = root / rel_path
        if not fp.exists():
            continue
        try:
            source = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        seen: list[str] = []
        for line in sorted(lines):
            func_src = _enclosing_function_source(source, line)
            if func_src and func_src not in seen:
                seen.append(func_src)
        if seen:
            contexts[rel_path] = seen
    return contexts


def assemble_input(state: ReviewState) -> dict:
    """입력 스키마 검증 후 pr_context 생성. 반환: {"pr_context": str}."""
    inp = ReviewInput.model_validate({
        "diff": state.get("diff"),
        "file_paths": state.get("file_paths"),
        "repo_meta": state.get("repo_meta", {}),
    })

    parts = ["## DIFF", inp.diff.rstrip()]

    files_root = inp.repo_meta.get("files_root", "")
    if files_root:
        contexts = _function_contexts(inp.diff, files_root)
        if contexts:
            parts.append("")
            parts.append("## 변경 함수 컨텍스트 (변경 줄을 포함하는 함수 전문)")
            for rel_path, funcs in contexts.items():
                parts.append(f"### {rel_path}")
                for func_src in funcs:
                    parts.append("```python")
                    parts.append(func_src.rstrip())
                    parts.append("```")

    return {"pr_context": "\n".join(parts)}
