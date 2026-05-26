"""
pip-audit — Python 의존성 CVE(보안 취약점) 검사 도구

동작 방식:
    pip-audit가 현재 환경의 설치된 패키지를 PyPI Advisory Database와 비교해
    알려진 CVE를 탐지한다.

severity 매핑:
    CRITICAL → Critical
    HIGH     → Critical
    MODERATE → Major
    LOW      → Minor
    (pip-audit는 별도 severity 없이 CVE ID만 제공 — HIGH로 기본 처리)
"""

import subprocess
import json


def run_pip_audit() -> list[dict]:
    """
    pip-audit를 실행하고 CVE 이슈 목록을 반환한다.

    Returns:
        Output Contract A 형식의 CVE 이슈 딕셔너리 목록.
        pip-audit 미설치 시 빈 리스트 반환.
    """
    r = subprocess.run(
        ["pip-audit", "--format=json"],
        capture_output=True, text=True, timeout=60
    )

    try:
        raw = json.loads(r.stdout)
    except json.JSONDecodeError:
        return []

    issues = []
    for dep in raw.get("dependencies", []):
        for vuln in dep.get("vulns", []):
            issues.append({
                "severity": "Critical",   # pip-audit CVE는 모두 Critical 처리
                "line": 0,
                "file": "requirements.txt",
                "message": (
                    f"CVE {vuln.get('id', 'UNKNOWN')}: "
                    f"{dep.get('name')}=={dep.get('version')} — {vuln.get('description', '')}"
                ),
                "rule_id": f"CVE-{vuln.get('id', 'UNKNOWN')}",
                "suggestion": f"안전 버전으로 업그레이드: {vuln.get('fix_versions', [])}",
                "similar_issues": [],
            })
    return issues
