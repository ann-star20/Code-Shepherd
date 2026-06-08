"""
tool_router_agent 노드 — PR 맥락 기반 도구 선택

run_tools 앞에서 실행되는 노드.
pr_diff / tech_stack / previous_pr_issues 등을 분석해
이번 PR에 필요한 도구 목록(tool_plan)을 결정한다.

MVP: LLM 없이 규칙 기반으로 구현.
     확장 시 LLM 호출로 대체 가능 (llm_required 필드로 트리거 여부 결정).

출력:
    state["tool_plan"] = ToolPlan dict
    — run_tools 노드가 selected_tools를 읽어 실제 도구 실행
"""

import logging
from pathlib import Path

from dev2.schema import Dev2State, ToolPlan

logger = logging.getLogger(__name__)

# ── 상수 ──────────────────────────────────────────────────────────────────────

ALLOWED_TOOLS: set[str] = {
    "pylint", "radon", "bandit", "semgrep",
    "eslint", "npm_audit", "pip_audit",
    "roslyn", "htmlhint", "stylelint",
}

SECURITY_KEYWORDS: list[str] = [
    "auth", "login", "password", "token", "jwt", "session", "cookie",
    "sql", "query", "raw", "select ", "insert ", "update ", "delete ",
    "eval(", "exec(", "subprocess", "innerHTML", "mark_safe",
    "csrf_exempt", "permission", "admin", "payment", "billing",
    "os.system", "os.popen",  # shell/command injection
    "secret",                  # hardcoded secret variable names
    "pathlib",                 # path manipulation (potential traversal)
]

# previous_pr_issues에서 보안 강화 트리거 키워드
_SECURITY_PR_KEYWORDS: list[str] = [
    "sql injection", "sql 인젝션", "xss", "csrf",
    "인증", "인가", "auth", "permission",
]

# XSS 관련 키워드 (HTML semgrep 추가 조건)
_XSS_KEYWORDS: list[str] = ["innerHTML", "innerhtml", "xss", "mark_safe"]

# 의존성 파일 (pip_audit / npm_audit 트리거)
_PY_DEP_FILES: set[str] = {"requirements.txt", "pyproject.toml", "setup.py", "Pipfile"}
_JS_DEP_FILES: set[str] = {"package.json", "package-lock.json", "yarn.lock"}


# ── 내부 헬퍼 ─────────────────────────────────────────────────────────────────

def _extract_all_files(diff: str) -> list[str]:
    """
    unified diff에서 변경 파일 전체 추출.
    의존성 파일(.txt, .json 등)도 포함 — SUPPORTED_EXTENSIONS 미적용.
    """
    files = []
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            files.append(line[6:])
    return files


def _detect_risk_keywords(diff: str) -> list[str]:
    """diff 내용(추가 라인 기준)에서 보안 키워드 탐지."""
    content = " ".join(
        line[1:].lower()
        for line in diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    return [kw for kw in SECURITY_KEYWORDS if kw.lower() in content]


def _has_security_pr_history(previous_pr_issues: list[str]) -> bool:
    """이전 PR 이슈에 보안 관련 내용이 있으면 True."""
    combined = " ".join(previous_pr_issues).lower()
    return any(kw in combined for kw in _SECURITY_PR_KEYWORDS)


# ── 핵심 로직 ─────────────────────────────────────────────────────────────────

def build_tool_plan(
    diff: str,
    tech_stack: list[str],
    previous_pr_issues: list[str],
) -> ToolPlan:
    """
    PR 맥락을 분석해 ToolPlan을 생성한다.

    우선순위:
        1. 파일 확장자별 기본 도구 선택
        2. 보안 키워드 감지 시 보안 도구 추가
        3. 의존성 파일 변경 시 audit 도구 추가
        4. previous_pr_issues 보안 이력 있으면 강화

    Args:
        diff: unified diff 전체 문자열
        tech_stack: 개발자 기술 스택 (예: ["django", "python"])
        previous_pr_issues: 이전 PR 반복 이슈 목록

    Returns:
        ToolPlan — selected_tools, llm_required, reason 포함
    """
    all_files = _extract_all_files(diff)
    risk_keywords = _detect_risk_keywords(diff)
    has_security_history = _has_security_pr_history(previous_pr_issues)

    selected: set[str] = set()
    detected_languages: set[str] = set()
    dependency_changed = False
    reason: list[str] = []

    content_lower = diff.lower()
    has_xss = any(kw in content_lower for kw in _XSS_KEYWORDS)
    has_security_kw = bool(risk_keywords)

    for filepath in all_files:
        name = Path(filepath).name.lower()
        ext = Path(filepath).suffix.lower()

        # ── Python ──────────────────────────────────────────────────────────
        if ext == ".py":
            detected_languages.add("python")
            selected.update({"pylint", "radon"})
            reason.append(f"Python 파일 변경으로 pylint/radon 선택 ({filepath})")
            if has_security_kw:
                selected.update({"bandit", "semgrep"})
                reason.append("보안 키워드 감지로 bandit/semgrep 추가")

        # ── Python 의존성 ────────────────────────────────────────────────────
        elif name in _PY_DEP_FILES:
            dependency_changed = True
            selected.add("pip_audit")
            reason.append(f"Python 의존성 파일 변경으로 pip_audit 추가 ({name})")

        # ── JavaScript / TypeScript ─────────────────────────────────────────
        elif ext in (".js", ".jsx", ".ts", ".tsx"):
            detected_languages.add("javascript")
            selected.add("eslint")
            reason.append(f"JS/TS 파일 변경으로 eslint 선택 ({filepath})")
            if has_security_kw:
                selected.add("semgrep")
                reason.append("보안 키워드 감지로 semgrep 추가")

        # ── JS 의존성 ────────────────────────────────────────────────────────
        elif name in _JS_DEP_FILES:
            dependency_changed = True
            selected.add("npm_audit")
            reason.append(f"JS 의존성 파일 변경으로 npm_audit 추가 ({name})")

        # ── C# ──────────────────────────────────────────────────────────────
        elif ext == ".cs":
            detected_languages.add("csharp")
            selected.update({"roslyn", "semgrep"})
            reason.append(f"C# 파일 변경으로 roslyn/semgrep 선택 ({filepath})")

        # ── HTML ─────────────────────────────────────────────────────────────
        elif ext in (".html", ".htm"):
            detected_languages.add("html")
            selected.add("htmlhint")
            reason.append(f"HTML 파일 변경으로 htmlhint 선택 ({filepath})")
            if has_xss:
                selected.add("semgrep")
                reason.append("XSS 관련 키워드 감지로 semgrep 추가")

        # ── CSS ──────────────────────────────────────────────────────────────
        elif ext in (".css", ".scss"):
            detected_languages.add("css")
            selected.add("stylelint")
            reason.append(f"CSS 파일 변경으로 stylelint 선택 ({filepath})")

        # ── 알 수 없는 확장자 ────────────────────────────────────────────────
        elif has_security_kw:
            selected.add("semgrep")
            reason.append(f"알 수 없는 확장자이나 보안 키워드 감지로 semgrep 선택 ({filepath})")

    # ── previous_pr_issues 보안 이력 → 보안 스캔 강화 ────────────────────────
    if has_security_history:
        if "python" in detected_languages:
            selected.update({"bandit", "semgrep"})
        if "javascript" in detected_languages:
            selected.add("semgrep")
        reason.append("이전 PR 보안 이슈 이력으로 보안 스캔 강화")

    # ALLOWED_TOOLS 필터 (정의 외 도구 제거)
    selected = selected & ALLOWED_TOOLS

    # llm_required: 보안 키워드 있거나 보안 이력 있으면 True
    llm_required = bool(has_security_kw or has_security_history or "bandit" in selected)

    return ToolPlan(
        changed_files=all_files,
        detected_languages=sorted(detected_languages),
        risk_keywords=risk_keywords,
        dependency_changed=dependency_changed,
        selected_tools=sorted(selected),
        llm_required=llm_required,
        reason=list(dict.fromkeys(reason)),  # 중복 제거, 순서 유지
    )


# ── LangGraph 노드 ────────────────────────────────────────────────────────────

async def tool_router_agent_node(state: Dev2State) -> dict:
    """
    LangGraph 노드: PR 맥락 기반 도구 선택.

    run_tools 앞에서 실행되어 state["tool_plan"]을 채운다.
    run_tools는 tool_plan.selected_tools를 참고해 필요한 도구만 실행한다.

    Args:
        state: Dev2State — pr_diff, tech_stack, previous_pr_issues 사용

    Returns:
        {"tool_plan": dict} — ToolPlan.model_dump()
    """
    diff: str = state.get("pr_diff", "")
    tech_stack: list[str] = state.get("tech_stack", [])  # type: ignore
    previous_pr_issues: list[str] = state.get("previous_pr_issues", [])  # type: ignore

    if not diff:
        logger.warning("tool_router_agent: pr_diff 없음 — 빈 tool_plan 반환")
        plan = ToolPlan(reason=["pr_diff 없음 — 도구 선택 불가"])
        return {"tool_plan": plan.model_dump()}

    plan = build_tool_plan(diff, tech_stack, previous_pr_issues)

    logger.info(
        "tool_router_agent: %d개 도구 선택 %s | llm_required=%s | risk_keywords=%d개",
        len(plan.selected_tools), plan.selected_tools,
        plan.llm_required, len(plan.risk_keywords),
    )
    return {"tool_plan": plan.model_dump()}
