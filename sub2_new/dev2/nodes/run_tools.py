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

    흐름:
        1. pr_diff 파싱 → 변경 파일 목록 추출
        2. detect_languages() → 언어별 파일 그룹핑
        3. asyncio.gather() → 언어별 _run_for_language 병렬 실행
        4. 결과 취합 → static_raw, security_raw 반환

    Args:
        state: Dev2State (pr_diff 필드 포함)

    Returns:
        {"static_raw": [...], "security_raw": [...]}
        — LangGraph가 이 dict를 state에 merge한다
    """
    diff = state.get("pr_diff", "")
    if not diff:
        logger.warning("run_tools_node: pr_diff가 비어 있음, 분석 생략")
        return {"static_raw": [], "security_raw": []}

    all_files = _extract_changed_files(diff)
    if not all_files:
        logger.warning("run_tools_node: 지원되는 변경 파일 없음 (diff 파일 수: %d줄)", len(diff.splitlines()))
        return {"static_raw": [], "security_raw": []}

    lang_groups = detect_languages(all_files)  # {"python": [...], "javascript": [...]}
    logger.info("run_tools_node: %d개 언어 감지 %s", len(lang_groups), list(lang_groups.keys()))

    # ── 언어별 도구 병렬 실행 (asyncio.gather + return_exceptions) ──────────
    # Week 5 교체 포인트: 타임아웃은 CLAUDE.md §6 기준 30초
    # common/harness.py의 run_parallel_agents()로 교체 시 이 gather 블록 제거
    tasks = [
        asyncio.wait_for(
            _run_for_language(lang, files),
            timeout=TOOL_TIMEOUT_SEC,
        )
        for lang, files in lang_groups.items()
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    static_raw: list[dict] = []
    security_raw: list[dict] = []

    for lang, result in zip(lang_groups.keys(), results):
        if isinstance(result, asyncio.TimeoutError):
            # CLAUDE.md §6: 타임아웃 → 해당 언어 결과 제외하고 진행
            logger.warning("run_tools_node: %s 도구 30초 타임아웃 — 결과 제외", lang)
            continue
        if isinstance(result, Exception):
            # CLAUDE.md §10-④: 에러는 삼키지 않는다 — 로그 후 계속
            logger.error("run_tools_node: %s 도구 실패 — %s", lang, result)
            continue
        static_raw.extend(result.get("static", []))
        security_raw.extend(result.get("security", []))

    logger.info(
        "run_tools_node 완료: static=%d개, security=%d개",
        len(static_raw), len(security_raw),
    )
    return {"static_raw": static_raw, "security_raw": security_raw}


async def _run_for_language(lang: str, files: list[str]) -> dict:
    """
    언어별 정적분석 + 보안 도구 실행.

    모든 동기 subprocess.run 호출은 asyncio.to_thread()로 스레드풀에 오프로드된다.
    → 이벤트 루프를 블록하지 않아 다른 언어 도구와 진정한 병렬 실행 가능.

    Args:
        lang: 언어 식별자 ("python", "javascript", "typescript", 등)
        files: 해당 언어의 변경 파일 경로 목록

    Returns:
        {"static": [...], "security": [...]}
    """
    runners = {
        "python":     _run_python,
        "javascript": _run_javascript,
        "typescript": _run_javascript,   # eslint로 TS도 처리
        "csharp":     _run_csharp,
        "html":       _run_html,
        "css":        _run_css,
    }
    runner = runners.get(lang, _run_generic)
    return await runner(files)


async def _run_python(files: list[str]) -> dict:
    """pylint + radon (정적) + bandit + semgrep (보안) 병렬 실행"""
    # asyncio.to_thread: 동기 subprocess.run을 스레드풀에서 실행 (Python 3.9+)
    # 두 그룹을 gather로 동시에 실행 (정적/보안 교차 병렬화)
    static_task = asyncio.to_thread(lambda: run_pylint(files) + run_radon(files))
    security_task = asyncio.to_thread(lambda: run_bandit(files) + run_semgrep(files, lang="python"))
    static, security = await asyncio.gather(static_task, security_task)
    return {"static": static, "security": security}


async def _run_javascript(files: list[str]) -> dict:
    """eslint (정적) + semgrep + npm audit (보안)"""
    static_task = asyncio.to_thread(lambda: run_eslint(files))
    # npm_audit는 파일 단위가 아닌 프로젝트 단위 — 별도 스레드 실행
    security_task = asyncio.to_thread(
        lambda: run_semgrep(files, lang="javascript") + run_npm_audit()
    )
    static, security = await asyncio.gather(static_task, security_task)
    return {"static": static, "security": security}


async def _run_csharp(files: list[str]) -> dict:
    """roslyn (정적) + semgrep (보안)"""
    static_task = asyncio.to_thread(lambda: run_roslyn(files))
    security_task = asyncio.to_thread(lambda: run_semgrep(files, lang="csharp"))
    static, security = await asyncio.gather(static_task, security_task)
    return {"static": static, "security": security}


async def _run_html(files: list[str]) -> dict:
    """htmlhint (정적) + semgrep (보안)"""
    static_task = asyncio.to_thread(lambda: run_htmlhint(files))
    security_task = asyncio.to_thread(lambda: run_semgrep(files, lang="html"))
    static, security = await asyncio.gather(static_task, security_task)
    return {"static": static, "security": security}


async def _run_css(files: list[str]) -> dict:
    """stylelint (정적만, CSS에는 별도 보안 도구 없음)"""
    static = await asyncio.to_thread(lambda: run_stylelint(files))
    return {"static": static, "security": []}


async def _run_generic(files: list[str]) -> dict:
    """알 수 없는 언어 → semgrep 공통 보안 검사만 실행"""
    security = await asyncio.to_thread(lambda: run_semgrep(files, lang="generic"))
    return {"static": [], "security": security}
