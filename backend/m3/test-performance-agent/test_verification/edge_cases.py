"""엣지케이스 누락 탐지 — TEST-003 Minor.

두 가지 모드:
  LLM 모드  : API 키(OPENAI_API_KEY / ANTHROPIC_API_KEY / GOOGLE_API_KEY) 있을 때
              함수 소스 → LLM 구조화 출력(Pydantic) → 누락 엣지케이스 목록
  휴리스틱 : 키 없을 때 인자명 기반 규칙 → 메시지에 [heuristic] 접두사

탐지기 6개 중 하나 — main.run()에서 test_verification 쪽으로 연결됨
"""
from __future__ import annotations

import ast
import os
from pathlib import Path

from pydantic import BaseModel

from contracts import Issue
from harness import instrument


# ── Pydantic 구조화 출력 모델 ─────────────────────────────
class EdgeCaseResult(BaseModel):
    missing: list[str]  # 빠진 엣지케이스 설명 목록


# ── 휴리스틱 규칙: 인자명 부분문자열 → 놓치기 쉬운 엣지케이스 ──────
# key = 인자명에 포함되면 일치하는 소문자 패턴
# value = 제안할 엣지케이스 목록
_HEURISTIC_RULES: dict[str, list[str]] = {
    "price":    ["0 (zero price)", "negative price"],
    "cost":     ["0 (zero cost)", "negative cost"],
    "amount":   ["0 (zero amount)", "negative amount"],
    "rate":     ["negative rate", "rate > 1"],
    "discount": ["negative discount", "discount > 1"],
    "ratio":    ["negative ratio", "ratio > 1"],
    "ids":      ["empty list []", "None"],
    "count":    ["0 (zero count)", "negative count"],
    "num":      ["0 (zero)", "negative"],
    "items":    ["empty list []", "None"],
    "values":   ["empty list []", "None"],
    "data":     ["empty", "None"],
    "text":     ["empty string ''", "None"],
    "name":     ["empty string ''", "None"],
    "message":  ["empty string ''", "None"],
    "index":    ["negative index", "out-of-bounds index"],
    "limit":    ["0 (zero limit)", "negative limit"],
    "size":     ["0 (zero size)", "negative size"],
}


def _has_llm_key() -> bool:
    return any(
        os.getenv(k)
        for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY")
    )


def _heuristic_missing(param_names: list[str]) -> list[str]:
    """인자명에 heuristic 키워드가 포함되면 누락 엣지케이스 목록 반환."""
    missing: list[str] = []
    triggered: set[str] = set()
    for pname in param_names:
        lower = pname.lower()
        for keyword, cases in _HEURISTIC_RULES.items():
            if keyword in lower and keyword not in triggered:
                triggered.add(keyword)
                missing.extend(cases)
    return missing


@instrument("edge_cases_llm", "llm")
def _llm_detect_missing(func_source: str) -> list[str]:
    """LLM(Gemini 2.5 Flash)에 함수 소스를 주고 빠진 엣지케이스 목록을 반환.

    테스트에서는 이 함수를 mock한다.
    실제 구현: Google Gemini structured output (JSON) 사용.
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return []

    try:
        import json  # noqa: PLC0415
        from google import genai  # noqa: PLC0415
        from google.genai import types  # noqa: PLC0415
        from config.settings import LLM_MODEL  # noqa: PLC0415

        client = genai.Client(api_key=api_key)
        prompt = (
            "You are a code reviewer. Analyze the function and list edge cases "
            "that should be tested but appear to be missing. Focus on: null/None "
            "inputs, zero values, negative values, empty collections, and boundary "
            "conditions. Respond as JSON: {\"missing\": [\"case1\", \"case2\"]}\n\n"
            f"Function:\n{func_source}"
        )
        resp = client.models.generate_content(
            model=LLM_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        data = json.loads(resp.text)
        return list(data.get("missing", []))
    except Exception:
        return []


def _detect_in_source(source: str, rel_path: str) -> list[Issue]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    use_llm = _has_llm_key()
    issues: list[Issue] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        # 인자 목록 추출 (self/cls 제외)
        params = [
            arg.arg for arg in node.args.args
            if arg.arg not in ("self", "cls")
        ]
        params += [arg.arg for arg in node.args.kwonlyargs]

        if not params:
            continue  # 무인자 함수 → spec §7.3 "0 issue"

        if use_llm:
            func_source = ast.get_source_segment(source, node) or ""
            missing = _llm_detect_missing(func_source)
            if missing:
                issues.append(
                    Issue(
                        severity="Minor",
                        file=rel_path,
                        line=node.lineno,
                        message=(
                            f"함수 '{node.name}': 빠진 엣지케이스 — "
                            + ", ".join(missing)
                        ),
                        rule_id="TEST-003",
                        suggestion="누락된 엣지케이스에 대한 단위 테스트를 추가하세요.",
                        keyword="엣지케이스 누락",
                        sub_category="null·빈값 미처리",
                    )
                )
        else:
            missing = _heuristic_missing(params)
            if missing:
                issues.append(
                    Issue(
                        severity="Minor",
                        file=rel_path,
                        line=node.lineno,
                        message=(
                            f"[heuristic] 함수 '{node.name}': "
                            f"빠진 엣지케이스 — "
                            + ", ".join(missing)
                        ),
                        rule_id="TEST-003",
                        suggestion="누락된 엣지케이스에 대한 단위 테스트를 추가하세요.",
                        keyword="엣지케이스 누락",
                        sub_category="null·빈값 미처리",
                    )
                )

    return issues


@instrument("edge_cases")
def detect(repo_path: str, changed: dict[str, set[int]]) -> list[Issue]:
    """Detect missing edge cases in changed Python functions."""
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


if __name__ == "__main__":
    import sys
    import textwrap

    print("=== edge_cases.py standalone 테스트 ===")
    sample = textwrap.dedent("""
        def calc_price(price, rate):
            return price * (1 - rate)

        def get_all():
            return []
    """)

    import tempfile, json
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "src"
        src.mkdir()
        (src / "sample.py").write_text(sample, encoding="utf-8")
        result = detect(tmp, {"src/sample.py": set(range(1, 50))})
        for i in result:
            print(json.dumps(i.model_dump(), ensure_ascii=False, indent=2))
    print(f"총 이슈: {len(result)}")
