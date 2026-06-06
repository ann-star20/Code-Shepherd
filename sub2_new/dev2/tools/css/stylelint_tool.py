"""
Stylelint — CSS / SCSS 정적 분석 도구

주요 탐지 항목:
    - 잘못된 단위 사용
    - 선택자 특이성 과잉
    - 미사용 변수 (SCSS)
    - 브라우저 호환성 문제

severity 매핑:
    error   → Major
    warning → Minor
"""

import subprocess
import json


def run_stylelint(files: list[str]) -> list[dict]:
    """
    Stylelint를 실행하고 이슈 목록을 반환한다.

    Args:
        files: 분석할 .css/.scss 파일 경로 목록

    Returns:
        Output Contract A 형식의 이슈 딕셔너리 목록.
        stylelint 미설치 또는 JSON 파싱 실패 시 빈 리스트 반환.
    """
    if not files:
        return []

    r = subprocess.run(
        ["stylelint", "--formatter=json"] + files,
        capture_output=True, text=True, timeout=30
    )

    try:
        raw = json.loads(r.stdout)
    except json.JSONDecodeError:
        return []

    issues = []
    for file_result in raw:
        for w in file_result.get("warnings", []):
            issues.append({
                "severity": "Major" if w.get("severity") == "error" else "Minor",
                "line": w.get("line", 0),
                "file": file_result.get("source", ""),
                "message": w.get("text", ""),
                "rule_id": f"CSS-{w.get('rule', 'UNKNOWN')}",
                "suggestion": f"Stylelint rule: {w.get('rule', '')}",
                "similar_issues": [],
            })
    return issues
