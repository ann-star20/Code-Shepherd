"""함수 한 줄 설명 생성 — Issue.code_context (Dev4 요청).

이슈가 가리키는 함수의 소스를 추출(AST=사실)해 LLM(Gemini)에게 한 줄 설명을
받아 issue.code_context에 채운다. 환각 방지: 설명만, 판정엔 관여 안 함.

- API 키(GOOGLE_API_KEY) 없으면 비활성(dormant): code_context는 빈 값으로 남음.
- 출력 계약(AgentOutput) 불변 — Issue 선택 필드 code_context만 채움.
- 같은 함수의 여러 이슈는 LLM 1회만 호출(캐시).
- 테스트에서는 describe를 주입하거나 _has_llm_key/describe_function을 monkeypatch.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path

from contracts import Issue
from harness import instrument


def _has_llm_key() -> bool:
    return bool(os.getenv("GOOGLE_API_KEY"))


@instrument("code_context_llm", "llm")
def describe_function(func_source: str) -> str:
    """함수 소스를 LLM(Gemini 2.5 Flash)에 주고 한 줄 설명을 받는다.

    키 없거나 실패하면 빈 문자열(안전). 테스트에서는 이 함수를 mock한다.
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return ""
    try:
        import json  # noqa: PLC0415
        from google import genai  # noqa: PLC0415
        from google.genai import types  # noqa: PLC0415
        from config.settings import LLM_MODEL  # noqa: PLC0415

        client = genai.Client(api_key=api_key)
        prompt = (
            "다음 파이썬 함수가 무엇을 하는지 한국어 한 문장으로 짧게 설명하세요. "
            '예: "장바구니 항목을 불러오는 함수". '
            '추측·평가는 하지 말고 코드가 하는 일만. JSON으로만: {"description": "..."}\n\n'
            f"함수:\n{func_source}"
        )
        resp = client.models.generate_content(
            model=LLM_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        data = json.loads(resp.text)
        return str(data.get("description", "")).strip()
    except Exception:
        return ""


def _enclosing_function(source: str, line: int) -> tuple[str, str]:
    """주어진 줄을 포함하는 가장 안쪽 함수의 (소스, 이름). 없으면 ("", "")."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return "", ""
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
        return "", ""
    return ast.get_source_segment(source, best[2]) or "", best[2].name


def augment_issues(issues: list[Issue], repo_path: str, describe=None) -> None:
    """각 이슈가 가리키는 함수를 추출해 code_snippet·name_of_function·code_context를 채운다(제자리).

    - code_snippet     = 함수 전체 소스 (AST=사실). LLM 키 없이도 항상 채움.
    - name_of_function = 그 함수 이름 (AST=사실). LLM 키 없이도 항상 채움.
    - code_context     = 그 함수의 한 줄 LLM 설명. 키 있을 때만 채움(없으면 빈 값).
    describe 주입 가능(테스트용); 미주입 시 모듈의 describe_function 사용.
    함수 못 찾으면 둘 다 빈 값으로 남음. 같은 함수의 설명은 1회만 호출(캐시).
    """
    has_key = _has_llm_key()
    if describe is None:
        describe = describe_function
    repo = Path(repo_path)
    cache: dict[str, str] = {}
    for issue in issues:
        if issue.line is None or not issue.file:
            continue
        try:
            source = (repo / issue.file).read_text(encoding="utf-8")
        except OSError:
            continue
        func_source, func_name = _enclosing_function(source, issue.line)
        if not func_source:
            continue
        issue.code_snippet = func_source       # AST=사실, 키 없이도 항상
        issue.name_of_function = func_name     # AST=사실, 키 없이도 항상
        if has_key:                            # LLM 설명은 키 있을 때만
            if func_source not in cache:
                cache[func_source] = describe(func_source)
            issue.code_context = cache[func_source]
