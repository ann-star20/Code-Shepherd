"""Dev2(정적분석·보안) 에이전트 어댑터 — 게이트웨이에 분석 함수를 등록.

★ 게이트웨이 규약 준수:
   - analyze(ctx: PRContext) -> list[dict]
   - 반환 dict: 표준 Issue 형식 (severity/file/line/message/rule_id/suggestion/_agent)

★ 내부 구현:
   - ctx.work_dir: clone된 코드 경로
   - ctx.pr_diff: unified diff (변경 파일 추출용)
   - Dev2 도구 직접 호출 (pylint / bandit / semgrep / eslint 등)
   - DB 저장·GitHub 코멘트·Slack 알림은 게이트웨이가 처리 → 여기서는 하지 않음
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from registry import PRContext, register

# ── Dev2 모듈 경로 주입 ────────────────────────────────────────────────────────
# webhook-gateway/agents/ → webhook-gateway/ → dev2/
_GW_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # webhook-gateway/
_DEV2_PARENT = os.path.dirname(_GW_DIR)                                  # dev2/../  (sub2_new)

for _p in (_GW_DIR, _DEV2_PARENT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ── 지원 확장자 (run_tools.py와 동일) ─────────────────────────────────────────
_SUPPORTED_EXT = {
    ".py", ".js", ".jsx", ".ts", ".tsx",
    ".cs", ".html", ".htm", ".css", ".scss",
}

# ── 도구 타임아웃 ──────────────────────────────────────────────────────────────
_TOOL_TIMEOUT = 30  # 초 (CLAUDE.md §6)


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

def _extract_changed_files(diff: str, work_dir: str) -> list[str]:
    """unified diff에서 변경 파일 추출 → work_dir 기준 절대경로 반환.

    존재하지 않는 파일은 제외한다 (삭제된 파일 등).
    """
    abs_files: list[str] = []
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            rel = line[6:]
            if Path(rel).suffix.lower() in _SUPPORTED_EXT:
                abs_path = os.path.join(work_dir, rel)
                if os.path.isfile(abs_path):
                    abs_files.append(abs_path)
    return abs_files


def _collect_all_files(work_dir: str) -> list[str]:
    """diff가 없을 때 폴백 — work_dir 전체에서 지원 파일 수집."""
    result: list[str] = []
    for root, _, filenames in os.walk(work_dir):
        for fname in filenames:
            if Path(fname).suffix.lower() in _SUPPORTED_EXT:
                result.append(os.path.join(root, fname))
    return result


def _tag(issues: list[dict], agent_name: str) -> list[dict]:
    """이슈 목록에 _agent 필드를 추가한다."""
    return [{**i, "_agent": agent_name} for i in issues]


def _run_python_static(files: list[str]) -> list[dict]:
    from dev2.tools.python.pylint_tool import run_pylint
    from dev2.tools.python.radon_tool import run_radon
    return run_pylint(files) + run_radon(files)


def _run_python_security(files: list[str]) -> list[dict]:
    from dev2.tools.python.bandit_tool import run_bandit
    from dev2.tools.common.semgrep_tool import run_semgrep
    return run_bandit(files) + run_semgrep(files, lang="python")


def _run_js_static(files: list[str]) -> list[dict]:
    from dev2.tools.javascript.eslint_tool import run_eslint
    return run_eslint(files)


def _run_js_security(files: list[str]) -> list[dict]:
    from dev2.tools.common.semgrep_tool import run_semgrep
    return run_semgrep(files, lang="javascript")


def _run_generic_security(files: list[str]) -> list[dict]:
    from dev2.tools.common.semgrep_tool import run_semgrep
    return run_semgrep(files, lang="generic")


# ── 정적분석 에이전트 등록 ────────────────────────────────────────────────────

@register("static_analysis")
def analyze_static(ctx: PRContext) -> list[dict]:
    """Pylint / ESLint / Radon 정적분석 → 이슈 목록 반환."""
    if not ctx.work_dir or not os.path.isdir(ctx.work_dir):
        return []

    files = (
        _extract_changed_files(ctx.pr_diff, ctx.work_dir)
        if ctx.pr_diff
        else _collect_all_files(ctx.work_dir)
    )
    if not files:
        return []

    from dev2.tools.router import detect_languages
    lang_groups = detect_languages(files)

    issues: list[dict] = []
    for lang, lang_files in lang_groups.items():
        if lang == "python":
            issues += _run_python_static(lang_files)
        elif lang in ("javascript", "typescript"):
            issues += _run_js_static(lang_files)
        # html/css/csharp: 정적 도구 결과도 static_analysis로 태깅
        # (별도 도구 호출 생략 — 필요 시 확장)

    return _tag(issues, "static_analysis")


# ── 보안 스캔 에이전트 등록 ───────────────────────────────────────────────────

@register("security_scan")
def analyze_security(ctx: PRContext) -> list[dict]:
    """Bandit / Semgrep / npm-audit 보안 스캔 → 이슈 목록 반환."""
    if not ctx.work_dir or not os.path.isdir(ctx.work_dir):
        return []

    files = (
        _extract_changed_files(ctx.pr_diff, ctx.work_dir)
        if ctx.pr_diff
        else _collect_all_files(ctx.work_dir)
    )
    if not files:
        return []

    from dev2.tools.router import detect_languages
    lang_groups = detect_languages(files)

    issues: list[dict] = []
    for lang, lang_files in lang_groups.items():
        if lang == "python":
            issues += _run_python_security(lang_files)
        elif lang in ("javascript", "typescript"):
            issues += _run_js_security(lang_files)
        else:
            issues += _run_generic_security(lang_files)

    return _tag(issues, "security_scan")
