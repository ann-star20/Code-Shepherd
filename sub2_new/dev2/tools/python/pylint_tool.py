"""
Pylint — Python 코드 품질 정적 분석 도구

Pylint 메시지 타입 → severity 매핑:
    E (Error)   → Critical  : 코드 버그, 정의되지 않은 변수 등
    F (Fatal)   → Critical  : 파싱 실패 등
    W (Warning) → Major     : 잠재적 버그, 사용되지 않는 변수
    C (Convention) → Minor  : PEP8 스타일 위반
    R (Refactor)   → Minor  : 리팩토링 권고

출력: Output Contract A 형식 (CLAUDE.md §5-A)
"""

import subprocess
import json

SEVERITY_MAP = {
    "E": "Critical",
    "F": "Critical",
    "W": "Major",
    "C": "Minor",
    "R": "Minor",
}


def run_pylint(files: list[str]) -> list[dict]:
    """
    Pylint를 실행하고 이슈 목록을 반환한다.

    Args:
        files: 분석할 .py 파일 경로 목록

    Returns:
        Output Contract A 형식의 이슈 딕셔너리 목록.
        Pylint 미설치 또는 JSON 파싱 실패 시 빈 리스트 반환 (CLAUDE.md §12).
    """
    if not files:
        return []

    r = subprocess.run(
        ["python", "-m", "pylint", "--output-format=json", "--score=no"] + files,
        capture_output=True, text=True, timeout=30
    )

    try:
        raw = json.loads(r.stdout)
    except json.JSONDecodeError:
        return []

    return [
        {
            "severity": SEVERITY_MAP.get(i.get("type", "W")[0].upper(), "Minor"),
            "line": i.get("line", 0),
            "file": i.get("path", ""),
            "message": i.get("message", ""),
            "rule_id": f"SA-{i.get('message-id', 'UNKNOWN')}",
            "suggestion": f"Pylint: {i.get('symbol', '')}",
            "similar_issues": [],
        }
        for i in raw

    ]
 

 