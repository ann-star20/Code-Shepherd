"""
Semgrep — 전 언어 공통 보안 정적 분석 도구 (OWASP Top 10 룰셋)

Semgrep의 강점:
    - 언어 무관하게 동일한 패턴 언어로 보안 룰 적용
    - OWASP Top 10: SQL 인젝션, XSS, CSRF, 인증 결함 등 탐지
    - 커스텀 룰 추가 가능 (p/owasp-top-ten, p/python, p/javascript 등)

severity 매핑:
    ERROR   → Critical
    WARNING → Major
    INFO    → Minor
"""

import importlib.util
import json
import logging
import os
import shutil
import subprocess
import sys

logger = logging.getLogger(__name__)

SEVERITY_MAP = {
    "ERROR": "Critical",
    "WARNING": "Major",
    "INFO": "Minor",
}


def _resolve_semgrep_cmd() -> list[str] | None:
    """
    실행 가능한 semgrep 호출 커맨드를 반환한다. 사용 불가 시 None.

    우선순위:
        1. PATH의 `semgrep` 실행파일 (Docker/Linux/Mac, WSL 패스스루 포함)
        2. `python -m semgrep` (실행파일이 PATH에 없지만 모듈은 설치된 환경)

    ⚠️ semgrep core(core_runner)는 Unix 전용 `resource` 모듈에 의존해
       Windows 네이티브에서는 실행되지 않는다. 이 경우 None을 반환해
       호출 측이 graceful skip 하도록 한다 (CLAUDE.md §12).
    """
    exe = shutil.which("semgrep")
    if exe:
        return [exe]
    # PATH에 실행파일이 없을 때: Windows 네이티브는 모듈 실행도 실패하므로 건너뜀
    if os.name == "nt":
        return None
    if importlib.util.find_spec("semgrep") is not None:
        return [sys.executable, "-m", "semgrep"]
    return None


def run_semgrep(files: list[str], lang: str = "generic") -> list[dict]:
    """
    Semgrep OWASP 룰셋으로 보안 취약점을 검사한다.

    Args:
        files: 분석할 파일 경로 목록
        lang: 언어 힌트 (현재는 미사용, 확장성을 위해 유지)

    Returns:
        Output Contract A 형식의 보안 이슈 딕셔너리 목록.
        semgrep 미설치/미지원(예: Windows) 또는 JSON 파싱 실패 시
        빈 리스트 반환 (CLAUDE.md §12 — 도구 부재가 파이프라인을 막지 않는다).
    """
    if not files:
        return []

    cmd = _resolve_semgrep_cmd()
    if cmd is None:
        logger.debug("run_semgrep: semgrep CLI 미사용(이 환경에서 실행 불가) — 건너뜀")
        return []

    try:
        r = subprocess.run(
            cmd + ["--config=p/owasp-top-ten", "--json", *files],
            capture_output=True, text=True, timeout=60,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        # 실행파일 부재(WinError 2)·타임아웃 등 → 에러로 전파하지 않고 건너뜀
        logger.debug("run_semgrep: 실행 실패(%s) — 건너뜀", type(exc).__name__)
        return []

    try:
        raw = json.loads(r.stdout)
    except json.JSONDecodeError:
        # semgrep 비정상 종료(stdout 비어있음) → 건너뜀
        logger.debug("run_semgrep: JSON 출력 없음(returncode=%s) — 건너뜀", r.returncode)
        return []

    return [
        {
            "severity": SEVERITY_MAP.get(
                i.get("extra", {}).get("severity", "WARNING"), "Major"
            ),
            "line": i.get("start", {}).get("line", 0),
            "file": i.get("path", ""),
            "message": i.get("extra", {}).get("message", ""),
            "rule_id": f"OWASP-{i.get('check_id', 'UNKNOWN').split('.')[-1]}",
            "suggestion": i.get("extra", {}).get("fix", "Semgrep OWASP 가이드 참조"),
            "similar_issues": [],
        }
        for i in raw.get("results", [])
    ]
