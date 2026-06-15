"""누락 함수 탐지 — 본문이 실행되지 않은 함수를 TEST-004 Minor로 보고.

핵심 원칙 (PRD §5.4):
  def 줄은 모듈 import 시 항상 실행됨 → def line만 보면 모든 함수가 covered로 오판.
  반드시 body[0].lineno ~ end_lineno 범위와 executed_lines 교집합으로 판정.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

from contracts import Issue
from harness import instrument


@instrument("missing_funcs")
def detect(repo_path: str, changed: dict[str, set[int]]) -> list[Issue]:
    """changed 파일 내 본문이 실행되지 않은 함수를 탐지한다."""
    cov_path = Path(repo_path) / "coverage.json"
    if not cov_path.exists():
        return []

    data = json.loads(cov_path.read_text(encoding="utf-8"))
    files_data = data.get("files", {})

    # coverage.json 키를 forward-slash로 정규화해 cross-platform 매칭
    normalized = {k.replace("\\", "/"): v for k, v in files_data.items()}

    issues: list[Issue] = []

    for rel_path in changed:
        norm_key = rel_path.replace("\\", "/")
        file_data = normalized.get(norm_key)
        if file_data is None:
            continue

        executed_lines = set(file_data.get("executed_lines", []))
        src_path = Path(repo_path) / Path(norm_key)
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

            # body-line 체크 — def-line 함정 방지
            body_start = node.body[0].lineno
            body_end = node.end_lineno or body_start
            body_lines = set(range(body_start, body_end + 1))

            if not (body_lines & executed_lines):
                issues.append(
                    Issue(
                        severity="Minor",
                        file=rel_path,
                        line=node.lineno,
                        message=f"함수 '{node.name}'에 대한 테스트 실행 흔적이 없습니다.",
                        rule_id="TEST-004",
                        suggestion=f"{node.name}()에 대한 단위 테스트를 추가하세요.",
                        keyword="테스트 누락",
                        sub_category="Untested Public Function",
                    )
                )

    return issues
