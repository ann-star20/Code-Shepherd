"""
Bandit — Python 보안 취약점 정적 분석 도구

주요 탐지 항목:
    - SQL 인젝션 (B608)
    - 하드코딩된 패스워드 (B105, B106)
    - eval/exec 사용 (B307)
    - 취약한 암호화 (B304, B305)
    - Shell injection (B602, B603)

Bandit severity → Dev2 severity 매핑:
    HIGH   → Critical
    MEDIUM → Major
    LOW    → Minor
"""

import subprocess
import json

SEVERITY_MAP = {
    "HIGH": "Critical",
    "MEDIUM": "Major",
    "LOW": "Minor",
}


def run_bandit(files: list[str]) -> list[dict]:
    """
    Bandit을 실행하고 보안 이슈 목록을 반환한다.

    Args:
        files: 분석할 .py 파일 경로 목록

    Returns:
        Output Contract A 형식의 보안 이슈 딕셔너리 목록.
        bandit 미설치 또는 JSON 파싱 실패 시 빈 리스트 반환.
    """
    if not files:
        return []

    r = subprocess.run(
        ["python", "-m", "bandit", "-r", "-f", "json"] + files,
        capture_output=True, text=True, timeout=30
    )

    try:
        raw = json.loads(r.stdout)
    except json.JSONDecodeError:
        return []

    return [
        {
            "severity": SEVERITY_MAP.get(i.get("issue_severity", "LOW"), "Minor"),
            "line": i.get("line_number", 0),
            "file": i.get("filename", ""),
            "message": i.get("issue_text", ""),
            "rule_id": f"SEC-{i.get('test_id', 'UNKNOWN')}",
            "suggestion": i.get("more_info", "Bandit 보안 가이드 참조"),
            "similar_issues": [],
        }
        for i in raw.get("results", [])
    ]
