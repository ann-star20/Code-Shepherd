"""
HTMLHint — HTML 정적 분석 도구

주요 탐지 항목:
    - 인라인 이벤트 핸들러 (onerror, onclick 등) → XSS 위험
    - <script> 태그 안 eval 사용
    - 누락된 필수 속성 (alt, lang 등)
    - 중복 ID

severity 매핑:
    error   → Major
    warning → Minor
"""

import subprocess
import json


def run_htmlhint(files: list[str]) -> list[dict]:
    """
    HTMLHint를 실행하고 이슈 목록을 반환한다.

    Args:
        files: 분석할 .html/.htm 파일 경로 목록

    Returns:
        Output Contract A 형식의 이슈 딕셔너리 목록.
        htmlhint 미설치 또는 JSON 파싱 실패 시 빈 리스트 반환.
    """
    if not files:
        return []

    r = subprocess.run(
        ["htmlhint", "--format=json"] + files,
        capture_output=True, text=True, timeout=30
    )

    try:
        raw = json.loads(r.stdout)
    except json.JSONDecodeError:
        return []

    issues = []
    for file_result in raw:
        for msg in file_result.get("messages", []):
            issues.append({
                "severity": "Major" if msg.get("type") == "error" else "Minor",
                "line": msg.get("line", 0),
                "file": file_result.get("fileid", ""),
                "message": msg.get("message", ""),
                "rule_id": f"HTML-{msg.get('rule', {}).get('id', 'UNKNOWN')}",
                "suggestion": msg.get("rule", {}).get("description", ""),
                "similar_issues": [],
            })
    return issues
