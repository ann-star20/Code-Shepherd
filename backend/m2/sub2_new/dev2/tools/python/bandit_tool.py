"""
Bandit — Python 보안 취약점 정적 분석 도구

주요 탐지 항목:
    - SQL 인젝션 (B608)
    - 하드코딩된 패스워드 (B105, B106)
    - eval/exec 사용 (B307)
    - 취약한 암호화 (B304, B305)
    - Shell injection (B602, B603, B605)

Bandit severity → Dev2 severity 매핑:
    HIGH   → Critical
    MEDIUM → Major
    LOW    → Minor
"""

import ast
import re
import subprocess
import json

SEVERITY_MAP = {
    "HIGH": "Critical",
    "MEDIUM": "Major",
    "LOW": "Minor",
}

# B105/B106/B107이 놓치는 패턴: URL 자격증명, PREFIX가 붙은 시크릿 변수
_SECRET_PATTERNS = [
    # scheme://user:password@host
    (re.compile(r'\w+\s*=\s*["\'][\w+\-.]+://[^:/"\']+:[^@/"\']+@', re.IGNORECASE),
     "Hardcoded credentials in URL (user:password@host)"),
    # AWS_SECRET_KEY, JWT_SECRET, ADMIN_TOKEN 등 — 접두사가 붙어도 탐지
    (re.compile(r'[A-Z][A-Z0-9_]*(?:SECRET|TOKEN|KEY|PASSWORD|CREDENTIAL)[A-Z0-9_]*\s*=\s*["\'].{8,}["\']',
                re.IGNORECASE),
     "Hardcoded secret key or token"),
]

# Bandit이 없는 경로 탐색 탐지: pathlib division / os.path.join with user input
_PATH_TRAVERSAL_PATTERNS = [
    # BASE_DIR / filename  또는  UPLOAD_PATH / name 등 대문자 상수 / 소문자 변수
    re.compile(r'\b[A-Z][A-Z0-9_]+\s*/\s*([a-z_]\w*)'),
    # os.path.join(base, variable)
    re.compile(r'os\.path\.join\s*\([^)]+,\s*([a-z_]\w*)\s*\)'),
]


def _scan_hardcoded_secrets(files: list[str]) -> list[dict]:
    """B105/B106/B107이 탐지하지 못하는 URL 자격증명·PREFIX 시크릿 변수를 스캔한다."""
    results = []
    for filepath in files:
        try:
            lines = open(filepath, encoding="utf-8", errors="ignore").readlines()
        except OSError:
            continue
        for lineno, line in enumerate(lines, 1):
            for pattern, message in _SECRET_PATTERNS:
                if pattern.search(line):
                    results.append({
                        "severity": "Critical",
                        "line": lineno,
                        "file": filepath,
                        "message": message,
                        "rule_id": "SEC-B105",
                        "suggestion": "환경변수 또는 시크릿 매니저로 이동하세요.",
                        "similar_issues": [],
                    })
                    break
    return results


def _scan_path_traversal(files: list[str]) -> list[dict]:
    """Bandit이 탐지하지 못하는 경로 탐색 취약점을 스캔한다 (pathlib / variable, os.path.join)."""
    results = []
    for filepath in files:
        try:
            lines = open(filepath, encoding="utf-8", errors="ignore").readlines()
        except OSError:
            continue
        for lineno, line in enumerate(lines, 1):
            for pattern in _PATH_TRAVERSAL_PATTERNS:
                m = pattern.search(line)
                if m:
                    var = m.group(1)
                    results.append({
                        "severity": "Major",
                        "line": lineno,
                        "file": filepath,
                        "message": f"Potential path traversal: unsanitized variable '{var}' used in file path",
                        "rule_id": "SEC-PT001",
                        "suggestion": "경로를 resolve() 후 기준 디렉토리로 시작하는지 검증하세요.",
                        "similar_issues": [],
                    })
                    break
    return results


def _scan_missing_auth(files: list[str]) -> list[dict]:
    """AST 기반: current_user를 가져오지만 비교 없이 변형 연산 수행 시 인가 누락으로 탐지한다."""
    results = []
    for filepath in files:
        try:
            source = open(filepath, encoding="utf-8", errors="ignore").read()
            tree = ast.parse(source)
        except (OSError, SyntaxError):
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue

            # current_user 할당 찾기 (get_current_user 호출)
            auth_var = None
            auth_line = node.lineno
            for stmt in ast.walk(node):
                if not isinstance(stmt, ast.Assign):
                    continue
                val = stmt.value
                if not (isinstance(val, ast.Call)):
                    continue
                func = val.func
                func_name = getattr(func, 'attr', getattr(func, 'id', ''))
                if 'current_user' in func_name.lower() or 'get_user' in func_name.lower():
                    for t in stmt.targets:
                        if isinstance(t, ast.Name):
                            auth_var = t.id
                            auth_line = stmt.lineno
                            break

            if not auth_var:
                continue

            # auth_var가 조건식(if/compare)에 사용되는지 확인
            used_in_condition = False
            for stmt in ast.walk(node):
                if isinstance(stmt, (ast.If, ast.Compare)):
                    for n in ast.walk(stmt):
                        if isinstance(n, ast.Name) and n.id == auth_var:
                            used_in_condition = True
                            break

            if used_in_condition:
                continue

            # 변형 연산(del, .remove/.pop/.delete) 존재하는지 확인
            has_mutation = False
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.Delete):
                    has_mutation = True
                    break
                if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                    attr = getattr(stmt.value.func, 'attr', '')
                    if attr in ('remove', 'pop', 'delete', 'discard', 'clear', 'update'):
                        has_mutation = True
                        break

            if has_mutation:
                results.append({
                    "severity": "Critical",
                    "line": auth_line,
                    "file": filepath,
                    "message": (
                        f"Missing authorization check in '{node.name}': "
                        f"'{auth_var}' is retrieved but never compared before mutation"
                    ),
                    "rule_id": "SEC-AUTH001",
                    "suggestion": "현재 사용자가 해당 리소스를 변경할 권한이 있는지 확인하세요.",
                    "similar_issues": [],
                })

    return results


def run_bandit(files: list[str]) -> list[dict]:
    """
    Bandit을 실행하고 보안 이슈 목록을 반환한다.
    Bandit이 놓치는 URL 자격증명·API 키는 _scan_hardcoded_secrets로 보완한다.

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
        raw = {"results": []}

    bandit_results = [
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

    return bandit_results + _scan_hardcoded_secrets(files) + _scan_path_traversal(files) + _scan_missing_auth(files)
