"""
다국어 라우터 — 파일 확장자 → (언어, 정적분석 도구, 보안 도구, 의존성 도구) 매핑

디스패치 테이블 패턴:
    if/elif 체인 대신 딕셔너리로 확장자별 도구를 관리한다.
    새 언어 추가 시 LANGUAGE_TOOL_MAP에 한 줄만 추가하면 된다.

Week 5 교체 포인트: 없음 (라우터는 Dev2 내부 로직, 팀 공통 모듈 아님)
"""

from pathlib import Path

# (언어명, 정적분석 도구 목록, 보안 도구 목록, 의존성 감사 도구 목록)
LANGUAGE_TOOL_MAP: dict[str, tuple[str, list[str], list[str], list[str]]] = {
    ".py":   ("python",     ["pylint", "radon"],  ["bandit", "semgrep"], ["pip_audit"]),
    ".js":   ("javascript", ["eslint"],           ["semgrep"],           ["npm_audit"]),
    ".jsx":  ("javascript", ["eslint"],           ["semgrep"],           ["npm_audit"]),
    ".ts":   ("typescript", ["eslint_ts"],        ["semgrep"],           ["npm_audit"]),
    ".tsx":  ("typescript", ["eslint_ts"],        ["semgrep"],           ["npm_audit"]),
    ".cs":   ("csharp",     ["roslyn"],           ["semgrep"],           []),
    ".html": ("html",       ["htmlhint"],         ["semgrep"],           []),
    ".htm":  ("html",       ["htmlhint"],         ["semgrep"],           []),
    ".css":  ("css",        ["stylelint"],        [],                    []),
    ".scss": ("css",        ["stylelint"],        [],                    []),
}

# 알 수 없는 확장자의 기본값 (semgrep만 실행)
_UNKNOWN = ("unknown", [], ["semgrep"], [])


def detect_languages(files: list[str]) -> dict[str, list[str]]:
    """
    파일 목록을 언어별로 그룹핑한다.

    Args:
        files: 파일 경로 목록 (e.g. ["auth.py", "app.js"])

    Returns:
        {"python": ["auth.py"], "javascript": ["app.js"], ...}
    """
    groups: dict[str, list[str]] = {}
    for f in files:
        ext = Path(f).suffix.lower()
        lang = LANGUAGE_TOOL_MAP.get(ext, _UNKNOWN)[0]
        groups.setdefault(lang, []).append(f)
    return groups


def get_tools_for_file(filepath: str) -> tuple[str, list[str], list[str], list[str]]:
    """
    단일 파일의 확장자에 맞는 도구 목록을 반환한다.

    Returns:
        (언어명, 정적분석 도구 목록, 보안 도구 목록, 의존성 도구 목록)
        알 수 없는 확장자: ("unknown", [], ["semgrep"], [])
    """
    ext = Path(filepath).suffix.lower()
    return LANGUAGE_TOOL_MAP.get(ext, _UNKNOWN)
