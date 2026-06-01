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

import subprocess
import json

SEVERITY_MAP = {
    "ERROR": "Critical",
    "WARNING": "Major",
    "INFO": "Minor",
}


def run_semgrep(files: list[str], lang: str = "generic") -> list[dict]:
    """
    Semgrep OWASP 룰셋으로 보안 취약점을 검사한다.

    Args:
        files: 분석할 파일 경로 목록
        lang: 언어 힌트 (현재는 미사용, 확장성을 위해 유지)

    Returns:
        Output Contract A 형식의 보안 이슈 딕셔너리 목록.
        semgrep 미설치 또는 JSON 파싱 실패 시 빈 리스트 반환 (CLAUDE.md §12).
    """
    if not files:
        return []

    r = subprocess.run(
        ["semgrep", "--config=p/owasp-top-ten", "--json"] + files,
        capture_output=True, text=True, timeout=60
    )

    try:
        raw = json.loads(r.stdout)
    except json.JSONDecodeError:
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
