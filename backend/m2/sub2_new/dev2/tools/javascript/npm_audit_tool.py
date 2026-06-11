"""
npm audit — Node.js 의존성 CVE(보안 취약점) 검사 도구

npm audit severity → Dev2 severity 매핑:
    critical → Critical
    high     → Critical
    moderate → Major
    low      → Minor

주의: package.json이 있는 디렉터리에서 실행해야 한다.
      Docker 컨테이너 안에서 실행 시 npm install 선행 필요.
"""

import subprocess
import json

SEVERITY_MAP = {
    "critical": "Critical",
    "high": "Critical",
    "moderate": "Major",
    "low": "Minor",
}


def run_npm_audit() -> list[dict]:
    """
    npm audit --json 을 실행하고 CVE 이슈 목록을 반환한다.

    Returns:
        Output Contract A 형식의 CVE 이슈 딕셔너리 목록.
        npm 미설치 또는 package.json 없는 경우 빈 리스트 반환.
    """
    r = subprocess.run(
        ["npm", "audit", "--json"],
        capture_output=True, text=True, timeout=60
    )

    try:
        raw = json.loads(r.stdout)
    except json.JSONDecodeError:
        return []

    return [
        {
            "severity": SEVERITY_MAP.get(v.get("severity", "low"), "Minor"),
            "line": 0,
            "file": "package.json",
            "message": f"npm CVE: {v.get('name')} — {v.get('title', '')}",
            "rule_id": f"CVE-{v.get('cves', ['UNKNOWN'])[0]}",
            "suggestion": f"업그레이드: {v.get('fixAvailable', {}).get('version', '확인 필요')}",
            "similar_issues": [],
        }
        for v in raw.get("vulnerabilities", {}).values()
    ]
