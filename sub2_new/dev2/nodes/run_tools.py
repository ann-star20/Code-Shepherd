"""
run_tools 노드 — CLI 도구 다국어 병렬 실행

LangGraph StateGraph의 첫 번째 노드.
pr_diff에서 변경된 파일을 추출하고, 언어별로 CLI 도구를 asyncio 병렬 실행한다.

실행 패턴:
    asyncio.gather(*language_tasks)    # 언어별 병렬
        └─ asyncio.to_thread(sync_fn)  # 동기 subprocess → 스레드풀 오프로드

타임아웃: 각 언어별 30초 (CLAUDE.md §6)
에러 처리: return_exceptions=True → 실패 언어는 빈 결과로 대체 (CLAUDE.md §12)
"""

import asyncio
import logging
from pathlib import Path

from dev2.schema import Dev2State
from dev2.tools.router import detect_languages
from dev2.tools.python.pylint_tool import run_pylint
from dev2.tools.python.radon_tool import run_radon
from dev2.tools.python.bandit_tool import run_bandit
from dev2.tools.javascript.eslint_tool import run_eslint
from dev2.tools.javascript.npm_audit_tool import run_npm_audit
from dev2.tools.csharp.roslyn_tool import run_roslyn
from dev2.tools.html.htmlhint_tool import run_htmlhint
from dev2.tools.css.stylelint_tool import run_stylelint
from dev2.tools.common.semgrep_tool import run_semgrep

logger = logging.getLogger(__name__)

# pr_diff에서 추출할 지원 확장자
SUPPORTED_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx",
    ".cs", ".html", ".htm", ".css", ".scss",
}

# 도구 타임아웃 — CLAUDE.md §6: 30초
TOOL_TIMEOUT_SEC = 30.0


def _extract_changed_files(diff: str) -> list[str]:
    """
    unified diff에서 변경된 파일 경로를 추출한다.

    unified diff 형식에서 '+++ b/path/to/file' 줄이 변경된 파일을 나타낸다.
    지원되지 않는 확장자(예: .md, .txt)는 제외한다.

    Args:
        diff: unified diff 형식 문자열 (CLAUDE.md §5-B pr_diff)

    Returns:
        지원 확장자를 가진 변경 파일 경로 목록
    """
    files = []
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:]  # "+++ b/" 제거
            if Path(path).suffix.lower() in SUPPORTED_EXTENSIONS:
                files.append(path)
    return files


async def run_tools_node(state: Dev2State) -> dict:
    """
    LangGraph 노드: 변경된 파일에 CLI 도구를 언어별로 병렬 실행한다.

    tool_plan 우선: tool_router_agent가 state["tool_plan"]을 채웠으면
        changed_files와 selected_tools를 사용해 필요한 도구만 실행.
    fallback: tool_plan 없으면 pr_diff에서 파일 추출 + 언어별 전체 도구 실행.

    Args:
        state: Dev2State (pr_diff, tool_plan 필드 사용)

    Returns:
        {"static_raw": [...], "security_raw": [...]}
    """
    diff = state.get("pr_diff", "")
    tool_plan: dict | None = state.get("tool_plan")  # type: ignore

    # ── tool_plan 기반 실행 (tool_router_agent가 선택한 도구만) ─────────────
    if tool_plan and tool_plan.get("selected_tools"):
        selected_tools: set[str] = set(tool_plan["selected_tools"])
        all_files = tool_plan.get("changed_files") or _extract_changed_files(diff)
        if not all_files:
            logger.warning("run_tools_node: tool_plan 있지만 changed_files 없음")
            return {"static_raw": [], "security_raw": []}

        # 지원 확장자 파일만 필터
        all_files = [f for f in all_files if Path(f).suffix.lower() in SUPPORTED_EXTENSIONS]
        lang_groups = detect_languages(all_files)
        logger.info(
            "run_tools_node: tool_plan 기반 실행 — selected_tools=%s, 언어=%s",
            sorted(selected_tools), list(lang_groups.keys()),
        )
        runner_fn = lambda lang, files: _run_for_language(lang, files, selected_tools)
    else:
        # ── fallback: 기존 동작 (전체 도구 실행) ─────────────────────────────
        if not diff:
            logger.warning("run_tools_node: pr_diff가 비어 있음, 분석 생략")
            return {"static_raw": [], "security_raw": []}
        all_files = _extract_changed_files(diff)
        if not all_files:
            logger.warning("run_tools_node: 지원되는 변경 파일 없음")
            return {"static_raw": [], "security_raw": []}
        lang_groups = detect_languages(all_files)
        selected_tools = None  # type: ignore
        logger.info(
            "run_tools_node: fallback(tool_plan 없음) — %d개 언어 %s",
            len(lang_groups), list(lang_groups.keys()),
        )
        runner_fn = lambda lang, files: _run_for_language(lang, files, None)

    # ── 언어별 병렬 실행 ─────────────────────────────────────────────────────
    tasks = [
        asyncio.wait_for(runner_fn(lang, files), timeout=TOOL_TIMEOUT_SEC)
        for lang, files in lang_groups.items()
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    static_raw: list[dict] = []
    security_raw: list[dict] = []

    for lang, result in zip(lang_groups.keys(), results):
        if isinstance(result, asyncio.TimeoutError):
            logger.warning("run_tools_node: %s 도구 30초 타임아웃 — 결과 제외", lang)
            continue
        if isinstance(result, Exception):
            logger.error("run_tools_node: %s 도구 실패 — %s", lang, result)
            continue
        static_raw.extend(result.get("static", []))
        security_raw.extend(result.get("security", []))

    logger.info(
        "run_tools_node 완료: static=%d개, security=%d개",
        len(static_raw), len(security_raw),
    )
    return {"static_raw": static_raw, "security_raw": security_raw}


async def _run_for_language(
    lang: str,
    files: list[str],
    selected_tools: set[str] | None = None,
) -> dict:
    """
    언어별 정적분석 + 보안 도구 실행.

    selected_tools가 있으면 해당 도구만 실행.
    None이면 언어별 전체 도구 실행 (fallback).

    Args:
        lang: 언어 식별자 ("python", "javascript", "typescript", 등)
        files: 해당 언어의 변경 파일 경로 목록
        selected_tools: tool_router_agent가 선택한 도구 집합 (None이면 전체)

    Returns:
        {"static": [...], "security": [...]}
    """
    runners = {
        "python":     _run_python,
        "javascript": _run_javascript,
        "typescript": _run_javascript,
        "csharp":     _run_csharp,
        "html":       _run_html,
        "css":        _run_css,
    }
    runner = runners.get(lang, _run_generic)
    return await runner(files, selected_tools)


async def _run_python(files: list[str], st: set[str] | None = None) -> dict:
    """pylint + radon (정적) + bandit + semgrep (보안). st=None이면 전체 실행."""
    all_tools = st is None
    static_parts = []
    security_parts = []

    tasks = []
    labels = []
    if all_tools or "pylint" in (st or set()):
        tasks.append(asyncio.to_thread(run_pylint, files))
        labels.append("pylint")
    if all_tools or "radon" in (st or set()):
        tasks.append(asyncio.to_thread(run_radon, files))
        labels.append("radon")
    if all_tools or "bandit" in (st or set()):
        tasks.append(asyncio.to_thread(run_bandit, files))
        labels.append("bandit")
    if all_tools or "semgrep" in (st or set()):
        tasks.append(asyncio.to_thread(run_semgrep, files, "python"))
        labels.append("semgrep")

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for label, result in zip(labels, results):
        if isinstance(result, Exception):
            logger.warning("_run_python: %s 실패 — %s", label, result)
            continue
        if label in ("pylint", "radon"):
            static_parts.extend(result)
        else:
            security_parts.extend(result)

    return {"static": static_parts, "security": security_parts}


async def _run_javascript(files: list[str], st: set[str] | None = None) -> dict:
    """eslint (정적) + semgrep + npm audit (보안)."""
    all_tools = st is None
    static_parts: list[dict] = []
    security_parts: list[dict] = []

    tasks = []
    labels = []
    if all_tools or "eslint" in (st or set()):
        tasks.append(asyncio.to_thread(run_eslint, files))
        labels.append("eslint")
    if all_tools or "semgrep" in (st or set()):
        tasks.append(asyncio.to_thread(run_semgrep, files, "javascript"))
        labels.append("semgrep")
    if all_tools or "npm_audit" in (st or set()):
        tasks.append(asyncio.to_thread(run_npm_audit))
        labels.append("npm_audit")

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for label, result in zip(labels, results):
        if isinstance(result, Exception):
            logger.warning("_run_javascript: %s 실패 — %s", label, result)
            continue
        if label == "eslint":
            static_parts.extend(result)
        else:
            security_parts.extend(result)

    return {"static": static_parts, "security": security_parts}


async def _run_csharp(files: list[str], st: set[str] | None = None) -> dict:
    """roslyn (정적) + semgrep (보안)."""
    all_tools = st is None
    tasks, labels = [], []
    if all_tools or "roslyn" in (st or set()):
        tasks.append(asyncio.to_thread(run_roslyn, files))
        labels.append("roslyn")
    if all_tools or "semgrep" in (st or set()):
        tasks.append(asyncio.to_thread(run_semgrep, files, "csharp"))
        labels.append("semgrep")

    static_parts, security_parts = [], []
    for label, result in zip(labels, await asyncio.gather(*tasks, return_exceptions=True)):
        if isinstance(result, Exception):
            logger.warning("_run_csharp: %s 실패 — %s", label, result)
            continue
        (static_parts if label == "roslyn" else security_parts).extend(result)

    return {"static": static_parts, "security": security_parts}


async def _run_html(files: list[str], st: set[str] | None = None) -> dict:
    """htmlhint (정적) + semgrep (보안)."""
    all_tools = st is None
    tasks, labels = [], []
    if all_tools or "htmlhint" in (st or set()):
        tasks.append(asyncio.to_thread(run_htmlhint, files))
        labels.append("htmlhint")
    if all_tools or "semgrep" in (st or set()):
        tasks.append(asyncio.to_thread(run_semgrep, files, "html"))
        labels.append("semgrep")

    static_parts, security_parts = [], []
    for label, result in zip(labels, await asyncio.gather(*tasks, return_exceptions=True)):
        if isinstance(result, Exception):
            logger.warning("_run_html: %s 실패 — %s", label, result)
            continue
        (static_parts if label == "htmlhint" else security_parts).extend(result)

    return {"static": static_parts, "security": security_parts}


async def _run_css(files: list[str], st: set[str] | None = None) -> dict:
    """stylelint (정적만)."""
    all_tools = st is None
    if not (all_tools or "stylelint" in (st or set())):
        return {"static": [], "security": []}
    static = await asyncio.to_thread(run_stylelint, files)
    return {"static": static if not isinstance(static, Exception) else [], "security": []}


async def _run_generic(files: list[str], st: set[str] | None = None) -> dict:
    """알 수 없는 언어 → semgrep만."""
    all_tools = st is None
    if not (all_tools or "semgrep" in (st or set())):
        return {"static": [], "security": []}
    security = await asyncio.to_thread(run_semgrep, files, "generic")
    return {"static": [], "security": security if not isinstance(security, Exception) else []}
