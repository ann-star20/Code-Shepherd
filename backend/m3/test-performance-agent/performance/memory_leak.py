"""메모리 누수 패턴 탐지 — PERF-003 Minor.

AST 후보 탐지 두 가지 패턴:
  1. open()이 with/대입 없이 단독 호출 → 파일 핸들 누수
  2. 전역 list/dict에 함수 내부에서 append 누적 → 무한 증가

LLM 교차검증 (키 있으면):
  후보를 LLM에 "진짜 누수?" → confidence < 0.7 제외 (오탐↓)

두 가지 모드:
  LLM 모드  : API 키(OPENAI_API_KEY / ANTHROPIC_API_KEY / GOOGLE_API_KEY) 있을 때
  휴리스틱 : 키 없을 때 AST 후보 그대로 → 메시지에 [heuristic] 접두사

탐지기 6개 중 하나 — main.run()에서 performance 쪽으로 연결됨
"""
from __future__ import annotations

import ast
import os
from pathlib import Path

from pydantic import BaseModel

from contracts import Issue
from harness import instrument


# ── Pydantic 구조화 출력 모델 ─────────────────────────────
class LeakVerification(BaseModel):
    is_leak: bool
    confidence: float   # 0.0 ~ 1.0
    reason: str


# ── LLM key detection ─────────────────────────────────────
def _has_llm_key() -> bool:
    return any(
        os.getenv(k)
        for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY")
    )


# ── AST 후보 탐지 ─────────────────────────────────────────

def _find_unclosed_opens(tree: ast.AST) -> list[tuple[int, str]]:
    """open()이 ast.Expr에서 단독 호출되는 패턴 탐지.

    with open() / fh = open() 는 ast.With / ast.Assign이므로 탐지 안 됨.
    """
    results: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        # ast.Expr = 결과를 사용하지 않는 표현식 문(standalone call)
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            if isinstance(call.func, ast.Name) and call.func.id == "open":
                results.append((
                    node.lineno,
                    "open() called without with-statement or assignment (file handle leak)",
                ))
    return results


def _find_global_unbounded_appends(tree: ast.AST) -> list[tuple[int, str]]:
    """모듈 최상위 list/dict 변수에 함수 내부에서 append하는 패턴 탐지."""
    if not isinstance(tree, ast.Module):
        return []

    # 모듈 최상위에서 list/dict로 초기화된 이름 수집
    global_names: set[str] = set()
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and isinstance(stmt.value, (ast.List, ast.Dict)):
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    global_names.add(target.id)

    if not global_names:
        return []

    # 함수 안에서 전역 이름에 .append() 호출 탐지
    results: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for child in ast.walk(node):
            if not (isinstance(child, ast.Expr) and isinstance(child.value, ast.Call)):
                continue
            call = child.value
            if (
                isinstance(call.func, ast.Attribute)
                and call.func.attr == "append"
                and isinstance(call.func.value, ast.Name)
                and call.func.value.id in global_names
            ):
                results.append((
                    child.lineno,
                    f"global collection '{call.func.value.id}' grows unboundedly via append()",
                ))
    return results


# ── LLM 교차검증 ─────────────────────────────────────────

@instrument("memory_leak_llm", "llm")
def _llm_verify_leak(candidate_desc: str, source_context: str) -> LeakVerification:
    """후보를 LLM(Gemini 2.5 Flash)에 주고 진짜 누수인지 교차검증.

    테스트에서는 이 함수를 mock한다.
    실제 구현: Google Gemini structured output (JSON) 사용.
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return LeakVerification(is_leak=True, confidence=1.0, reason="heuristic_no_llm")

    try:
        import json  # noqa: PLC0415
        from google import genai  # noqa: PLC0415
        from google.genai import types  # noqa: PLC0415
        from config.settings import LLM_MODEL  # noqa: PLC0415

        client = genai.Client(api_key=api_key)
        prompt = (
            "You are a memory leak expert. Determine if the given code pattern "
            "represents a genuine memory leak. Respond as JSON: "
            "{\"is_leak\": true/false, \"confidence\": 0.0-1.0, \"reason\": \"...\"}\n\n"
            f"Candidate pattern: {candidate_desc}\n\nCode:\n{source_context}"
        )
        resp = client.models.generate_content(
            model=LLM_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        data = json.loads(resp.text)
        return LeakVerification(
            is_leak=bool(data.get("is_leak", False)),
            confidence=float(data.get("confidence", 0.0)),
            reason=str(data.get("reason", "gemini")),
        )
    except Exception:
        # LLM 실패 시 AST 후보 신뢰 (오탐보다 누락 방지 우선)
        return LeakVerification(is_leak=True, confidence=1.0, reason="llm_unavailable")


# ── 소스 단위 탐지 ─────────────────────────────────────────

def _detect_in_source(source: str, rel_path: str) -> list[Issue]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    use_llm = _has_llm_key()

    # AST 후보 수집
    candidates: list[tuple[int, str]] = []
    candidates.extend(_find_unclosed_opens(tree))
    candidates.extend(_find_global_unbounded_appends(tree))

    if not candidates:
        return []

    from config.settings import LLM_CONFIDENCE_MIN  # noqa: PLC0415

    issues: list[Issue] = []
    for lineno, desc in candidates:
        if use_llm:
            verification = _llm_verify_leak(desc, source)
            if not verification.is_leak or verification.confidence < LLM_CONFIDENCE_MIN:
                continue
            issues.append(
                Issue(
                    severity="Minor",
                    file=rel_path,
                    line=lineno,
                    message=f"메모리 누수 가능: {desc}",
                    rule_id="PERF-003",
                    suggestion="리소스를 명시적으로 닫거나 with 문을 사용하세요.",
                    keyword="메모리 누수",
                    sub_category="Unbounded Collection Growth",
                )
            )
        else:
            issues.append(
                Issue(
                    severity="Minor",
                    file=rel_path,
                    line=lineno,
                    message=f"[heuristic] 메모리 누수 가능: {desc}",
                    rule_id="PERF-003",
                    suggestion="리소스를 명시적으로 닫거나 with 문을 사용하세요.",
                    keyword="메모리 누수",
                    sub_category="Unbounded Collection Growth",
                )
            )

    return issues


@instrument("memory_leak")
def detect(repo_path: str, changed: dict[str, set[int]]) -> list[Issue]:
    """Detect memory leak patterns in changed Python files."""
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
    import json
    import tempfile
    import textwrap

    print("=== memory_leak.py standalone 테스트 ===")
    sample = textwrap.dedent("""
        EVENTS = []

        def log_event(evt):
            EVENTS.append(evt)

        def safe_read(path):
            with open(path) as f:
                return f.read()

        def bad_read(path):
            open(path)
    """)

    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "src"
        src.mkdir()
        (src / "sample.py").write_text(sample, encoding="utf-8")
        result = detect(tmp, {"src/sample.py": set(range(1, 50))})
        for i in result:
            print(json.dumps(i.model_dump(), ensure_ascii=False, indent=2))
    print(f"총 이슈: {len(result)}")
