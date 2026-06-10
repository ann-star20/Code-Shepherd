"""
ESLint — JavaScript / TypeScript 코드 품질 정적 분석 도구

ESLint severity 코드 → Dev2 severity 매핑:
    2 (error)   → Critical
    1 (warning) → Major
    0 (off)     → Minor

TypeScript 지원:
    ts=True 옵션으로 .ts/.tsx 확장자를 대상으로 설정.
    TypeScript 파서(@typescript-eslint/parser)가 설치되어 있어야 함.
"""

import subprocess
import json

SEVERITY_MAP = {
    2: "Critical",
    1: "Major",
    0: "Minor",
}


def run_eslint(files: list[str], ts: bool = False) -> list[dict]:
    """
    ESLint를 실행하고 이슈 목록을 반환한다.

    Args:
        files: 분석할 .js/.jsx (.ts/.tsx) 파일 경로 목록
        ts: TypeScript 모드 여부 (--ext .ts,.tsx 사용)

    Returns:
        Output Contract A 형식의 이슈 딕셔너리 목록.
        eslint 미설치 또는 JSON 파싱 실패 시 빈 리스트 반환.
    """
    if not files:
        return []

    ext_flag = "--ext .ts,.tsx" if ts else "--ext .js,.jsx"
    r = subprocess.run(
        ["eslint", "--format=json", ext_flag] + files,
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
                "severity": SEVERITY_MAP.get(msg.get("severity", 1), "Minor"),
                "line": msg.get("line", 0),
                "file": file_result.get("filePath", ""),
                "message": msg.get("message", ""),
                "rule_id": f"JS-{msg.get('ruleId', 'UNKNOWN')}",
                "suggestion": f"ESLint rule: {msg.get('ruleId', '')}",
                "similar_issues": [],
            })
    return issues
