"""m2 정적 분석·보안 스캔 — PR diff 기반 도구 실행.

계약: shared.contracts.IssueItem / IssueSummary / M2AnalyzeResponse.

m2 서비스는 오케스트레이터(m1)로부터 unified diff만 받는다(work_dir 없음).
따라서 diff의 post-image(추가·문맥 라인)를 임시 파일로 복원한 뒤 도구를 실행한다.

도구(pylint / radon / bandit / semgrep / eslint)가 설치돼 있지 않으면
빈 결과로 graceful skip 한다(루트 GLOBAL_AGENT_RULE / sub2 CLAUDE.md §12 —
도구 부재가 파이프라인을 막지 않는다).
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Literal

from shared.contracts import IssueItem, IssueSummary

Agent = Literal["static_analysis", "security_scan"]

_TOOL_TIMEOUT = 30  # 초
_SUPPORTED_EXT = {".py", ".js", ".jsx", ".ts", ".tsx"}

_LANG_BY_EXT = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
}

# 도구 severity → 계약 severity 매핑 (dev2 도구 정의와 동일)
_PYLINT_SEVERITY = {"E": "Critical", "F": "Critical", "W": "Major", "C": "Minor", "R": "Minor"}
_BANDIT_SEVERITY = {"HIGH": "Critical", "MEDIUM": "Major", "LOW": "Minor"}
_SEMGREP_SEVERITY = {"ERROR": "Critical", "WARNING": "Major", "INFO": "Minor"}
_ESLINT_SEVERITY = {2: "Critical", 1: "Major", 0: "Minor"}


# ── diff 파싱 ─────────────────────────────────────────────────────────────────

def _parse_diff(pr_diff: str) -> dict[str, str]:
    """unified diff → {relpath: post-image 내용}.

    post-image = 추가('+') 라인 + 문맥(' ') 라인. 삭제('-')는 제외한다.
    삭제된 파일(`+++ /dev/null`)은 건너뛴다.
    """
    files: dict[str, list[str]] = {}
    current: list[str] | None = None

    for line in pr_diff.splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip()
            if path.startswith("b/"):
                path = path[2:]
            current = None if (not path or path == "/dev/null") else files.setdefault(path, [])
            continue
        if line.startswith("--- ") or line.startswith("diff --git"):
            current = None
            continue
        if current is None:
            continue
        if line.startswith("@@") or line.startswith("\\"):
            continue
        if line.startswith("+"):
            current.append(line[1:])
        elif line.startswith(" "):
            current.append(line[1:])
        # 삭제('-')·기타 메타 라인은 무시

    return {rel: "\n".join(lines) + "\n" for rel, lines in files.items() if lines}


def _materialize(files: dict[str, str], root: str) -> list[str]:
    """복원된 파일을 임시 디렉토리에 기록 → 기록된 상대경로 목록 반환."""
    written: list[str] = []
    for rel, content in files.items():
        if Path(rel).suffix.lower() not in _SUPPORTED_EXT:
            continue
        abs_path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(abs_path) or root, exist_ok=True)
        Path(abs_path).write_text(content, encoding="utf-8")
        written.append(rel)
    return written


def _group_by_lang(paths: list[str]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for p in paths:
        lang = _LANG_BY_EXT.get(Path(p).suffix.lower(), "unknown")
        groups.setdefault(lang, []).append(p)
    return groups


# ── 도구 실행 ─────────────────────────────────────────────────────────────────

def _run(cmd: list[str], cwd: str) -> str | None:
    """서브프로세스 실행 → stdout 반환. 도구 부재·타임아웃 시 None(graceful skip)."""
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=_TOOL_TIMEOUT
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout


def _relativize(path: str, root: str) -> str:
    if path and os.path.isabs(path):
        try:
            path = os.path.relpath(path, root)
        except ValueError:
            pass
    normalized = (path or "").replace(os.sep, "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _resolve_semgrep() -> list[str] | None:
    """실행 가능한 semgrep 커맨드. Windows 네이티브 등 미지원 환경은 None."""
    exe = shutil.which("semgrep")
    if exe:
        return [exe]
    if os.name == "nt":
        return None
    if importlib.util.find_spec("semgrep") is not None:
        return [sys.executable, "-m", "semgrep"]
    return None


def _resolve_tool(name: str) -> list[str] | None:
    """시스템 PATH에서 도구 바이너리를 찾고, 없으면 sys.executable -m 으로 폴백."""
    exe = shutil.which(name)
    if exe:
        return [exe]
    # venv 외부 시스템 Python으로도 시도
    try:
        subprocess.run([sys.executable, "-m", name, "--version"],
                       capture_output=True, timeout=5)
        return [sys.executable, "-m", name]
    except Exception:
        return None


def _run_pylint(paths: list[str], cwd: str) -> list[IssueItem]:
    cmd = _resolve_tool("pylint")
    if cmd is None:
        return []
    out = _run([*cmd, "--output-format=json", "--score=no", *paths], cwd)
    if not out:
        return []
    try:
        raw = json.loads(out)
    except json.JSONDecodeError:
        return []
    return [
        IssueItem(
            severity=_PYLINT_SEVERITY.get(str(i.get("type", "W"))[:1].upper(), "Minor"),
            line=i.get("line"),
            file=i.get("path"),
            message=i.get("message", ""),
            rule_id=f"SA-{i.get('message-id', 'UNKNOWN')}",
            suggestion=f"pylint: {i.get('symbol', '')}",
        )
        for i in raw
    ]


def _run_radon(paths: list[str], cwd: str) -> list[IssueItem]:
    cmd = _resolve_tool("radon")
    if cmd is None:
        return []
    out = _run([*cmd, "cc", "--json", "--min", "B", *paths], cwd)
    if not out:
        return []
    try:
        raw = json.loads(out)
    except json.JSONDecodeError:
        return []
    items: list[IssueItem] = []
    for filepath, funcs in raw.items():
        if not isinstance(funcs, list):
            continue
        for func in funcs:
            cc = func.get("complexity", 0)
            if cc > 10:
                items.append(
                    IssueItem(
                        severity="Major",
                        line=func.get("lineno"),
                        file=filepath,
                        message=f"순환복잡도 {cc} 감지 (함수: {func.get('name')})",
                        rule_id="SA-COMPLEXITY",
                        suggestion="함수를 더 작은 단위로 분리하세요.",
                    )
                )
    return items


def _run_eslint(paths: list[str], cwd: str) -> list[IssueItem]:
    out = _run(["eslint", "--format=json", *paths], cwd)
    if not out:
        return []
    try:
        raw = json.loads(out)
    except json.JSONDecodeError:
        return []
    items: list[IssueItem] = []
    for file_result in raw:
        rel = _relativize(file_result.get("filePath", ""), cwd)
        for msg in file_result.get("messages", []):
            items.append(
                IssueItem(
                    severity=_ESLINT_SEVERITY.get(msg.get("severity", 1), "Minor"),
                    line=msg.get("line"),
                    file=rel,
                    message=msg.get("message", ""),
                    rule_id=f"JS-{msg.get('ruleId') or 'UNKNOWN'}",
                    suggestion=f"eslint: {msg.get('ruleId') or ''}",
                )
            )
    return items


def _run_bandit(paths: list[str], cwd: str) -> list[IssueItem]:
    cmd = _resolve_tool("bandit")
    if cmd is None:
        return []
    out = _run([*cmd, "-r", "-f", "json", *paths], cwd)
    if out is None:
        return []
    try:
        raw = json.loads(out or "{}")
    except json.JSONDecodeError:
        return []
    return [
        IssueItem(
            severity=_BANDIT_SEVERITY.get(i.get("issue_severity", "LOW"), "Minor"),
            line=i.get("line_number"),
            file=i.get("filename"),
            message=i.get("issue_text", ""),
            rule_id=f"SEC-{i.get('test_id', 'UNKNOWN')}",
            suggestion=i.get("more_info") or "Bandit 보안 가이드 참조",
        )
        for i in raw.get("results", [])
    ]


def _run_semgrep(paths: list[str], cwd: str) -> list[IssueItem]:
    cmd = _resolve_semgrep()
    if cmd is None:
        return []
    out = _run([*cmd, "--config=p/owasp-top-ten", "--json", *paths], cwd)
    if not out:
        return []
    try:
        raw = json.loads(out)
    except json.JSONDecodeError:
        return []
    return [
        IssueItem(
            severity=_SEMGREP_SEVERITY.get(
                i.get("extra", {}).get("severity", "WARNING"), "Major"
            ),
            line=i.get("start", {}).get("line"),
            file=i.get("path"),
            message=i.get("extra", {}).get("message", ""),
            rule_id=f"OWASP-{str(i.get('check_id', 'UNKNOWN')).split('.')[-1]}",
            suggestion=i.get("extra", {}).get("fix") or "Semgrep OWASP 가이드 참조",
        )
        for i in raw.get("results", [])
    ]


def _run_tools(rel_paths: list[str], cwd: str, agent: Agent) -> list[IssueItem]:
    issues: list[IssueItem] = []
    for lang, paths in _group_by_lang(rel_paths).items():
        if agent == "static_analysis":
            if lang == "python":
                issues += _run_pylint(paths, cwd)
                issues += _run_radon(paths, cwd)
            elif lang in ("javascript", "typescript"):
                issues += _run_eslint(paths, cwd)
        else:  # security_scan
            if lang == "python":
                issues += _run_bandit(paths, cwd)
                issues += _run_semgrep(paths, cwd)
            else:
                issues += _run_semgrep(paths, cwd)
    return issues


def _summarize(issues: list[IssueItem]) -> IssueSummary:
    summary = IssueSummary()
    for issue in issues:
        if issue.severity == "Critical":
            summary.critical += 1
        elif issue.severity == "Major":
            summary.major += 1
        else:
            summary.minor += 1
    return summary


# ── 공개 진입점 ───────────────────────────────────────────────────────────────

def analyze(pr_diff: str, agent: Agent) -> tuple[list[IssueItem], IssueSummary, int]:
    """PR diff를 분석해 (이슈 목록, 요약, 실행시간 ms)를 반환한다.

    diff가 비었거나 지원 파일이 없으면 빈 결과를 반환한다.
    """
    start = time.monotonic()
    files = _parse_diff(pr_diff or "")
    if not files:
        return [], IssueSummary(), int((time.monotonic() - start) * 1000)

    tmp = tempfile.mkdtemp(prefix="m2-")
    try:
        written = _materialize(files, tmp)
        issues = _run_tools(written, tmp, agent)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    for issue in issues:
        issue.file = _relativize(issue.file or "", tmp)

    return issues, _summarize(issues), int((time.monotonic() - start) * 1000)
