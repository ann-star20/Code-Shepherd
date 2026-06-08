"""
radon — Python 순환복잡도(Cyclomatic Complexity) 측정 도구

순환복잡도란?
    함수 안의 분기(if/for/while/try 등) 경로 수.
    복잡도가 높을수록 테스트·유지보수가 어렵다.

radon 등급 기준:
    A(1~5): 단순  → 무시
    B(6~10): 보통 → Minor (--min B 옵션으로 B부터 출력)
    C(11~15): 복잡 → Major (복잡도 > 10)
    D 이상: 매우 복잡 → Major

이 도구는 복잡도 > 10 인 함수만 이슈로 리포트한다.
"""

import subprocess
import json


def run_radon(files: list[str]) -> list[dict]:
    """
    radon cc 로 순환복잡도를 측정하고 이슈 목록을 반환한다.

    Args:
        files: 분석할 .py 파일 경로 목록

    Returns:
        복잡도 > 10 인 함수에 대한 이슈 딕셔너리 목록.
        radon 미설치 또는 JSON 파싱 실패 시 빈 리스트 반환.
    """
    if not files:
        return []

    r = subprocess.run(
        ["python", "-m", "radon", "cc", "--json", "--min", "B"] + files,
        capture_output=True, text=True, timeout=30
    )

    try:
        raw = json.loads(r.stdout)
    except json.JSONDecodeError:
        return []

    issues = []
    for filepath, funcs in raw.items():
        for func in funcs:
            cc = func.get("complexity", 0)
            if cc > 10:
                issues.append({
                    "severity": "Major",
                    "line": func.get("lineno", 0),
                    "file": filepath,
                    "message": f"순환복잡도 {cc} 감지. 함수: {func.get('name')}",
                    "rule_id": "SA-COMPLEXITY",
                    "suggestion": "함수를 더 작은 단위로 분리하세요.",
                    "similar_issues": [],
                })
    return issues
