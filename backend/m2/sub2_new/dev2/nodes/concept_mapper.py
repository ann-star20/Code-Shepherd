"""
concept_mapper — M4 학습 커리큘럼용 이슈 매핑

이슈의 rule_id / message 패턴을 분석해 M4가 학습자료를 생성할 때 필요한
concept / mistake_type / concept_id / confidence_score 등을 부여한다.

M2의 역할:
    - 이슈를 Concept/mistake_type에 매핑한 구조화 데이터 생성
    - 학습자료 직접 생성 금지 (M4 담당)
    - GitHub PR 코멘트 생성 금지 (M4 담당)

매핑 우선순위:
    1. rule_id 직접 매핑 (가장 정확, confidence 높음)
    2. message 패턴 매핑 (rule_id 미매핑 시)
    3. 미매핑 → 빈 문자열 유지 (concept = "", confidence = 0.0)

confidence 기준:
    0.8 이상 → mistake_type까지 명확 매핑
    0.8 미만 → concept만 채우고 mistake_type = "general"
"""

import ast
import re
from pathlib import Path

from dev2.schema import LearningContext

# ── rule_id 직접 매핑 ─────────────────────────────────────────────────────────
# Bandit / Semgrep / Pylint rule_id → concept 정보
RULE_CONCEPT_MAP: dict[str, dict] = {
    # SQL Injection
    "B608": {
        "keyword": "SQL Injection",
        "sub_category": "raw_query",
        "concept_id": "sql_injection",
        "mistake_type_concept_id": "sql_injection.raw_query",
        "confidence_score": 0.92,
    },
    "SEC-B608": {
        "keyword": "SQL Injection",
        "sub_category": "raw_query",
        "concept_id": "sql_injection",
        "mistake_type_concept_id": "sql_injection.raw_query",
        "confidence_score": 0.92,
    },
    # XSS
    "B703": {  # Django mark_safe
        "keyword": "XSS",
        "sub_category": "mark_safe_misuse",
        "concept_id": "xss",
        "mistake_type_concept_id": "xss.mark_safe_misuse",
        "confidence_score": 0.90,
    },
    "B308": {  # mark_safe
        "keyword": "XSS",
        "sub_category": "mark_safe_misuse",
        "concept_id": "xss",
        "mistake_type_concept_id": "xss.mark_safe_misuse",
        "confidence_score": 0.88,
    },
    # CSRF
    "B506": {
        "keyword": "CSRF",
        "sub_category": "csrf_exempt_misuse",
        "concept_id": "csrf",
        "mistake_type_concept_id": "csrf.csrf_exempt_misuse",
        "confidence_score": 0.88,
    },
    # 인증/인가
    "B324": {  # weak hash (MD5/SHA1)
        "keyword": "AUTH_VULNERABILITY",
        "sub_category": "weak_password_policy",
        "concept_id": "auth_vulnerability",
        "mistake_type_concept_id": "auth_vulnerability.weak_password_policy",
        "confidence_score": 0.90,
    },
    "B105": {  # hardcoded password
        "keyword": "AUTH_VULNERABILITY",
        "sub_category": "weak_password_policy",
        "concept_id": "auth_vulnerability",
        "mistake_type_concept_id": "auth_vulnerability.weak_password_policy",
        "confidence_score": 0.95,
    },
    "B106": {
        "keyword": "AUTH_VULNERABILITY",
        "sub_category": "weak_password_policy",
        "concept_id": "auth_vulnerability",
        "mistake_type_concept_id": "auth_vulnerability.weak_password_policy",
        "confidence_score": 0.95,
    },
}

# ── message 패턴 매핑 (rule_id 미매핑 시 사용) ────────────────────────────────
# (compiled pattern, mapping dict) 리스트 — 순서대로 매칭
_MESSAGE_PATTERNS: list[tuple[re.Pattern, dict]] = [
    (re.compile(r"sql\s*inject|parameteriz|raw.query|string.format.*sql|%.*sql", re.I), {
        "keyword": "SQL Injection",
        "sub_category": "no_parameterize",
        "concept_id": "sql_injection",
        "mistake_type_concept_id": "sql_injection.no_parameterize",
        "confidence_score": 0.75,
    }),
    (re.compile(r"mark_safe|safe\s+filter|autoescape.*off|innerHTML|inner_html", re.I), {
        "keyword": "XSS",
        "sub_category": "mark_safe_misuse",
        "concept_id": "xss",
        "mistake_type_concept_id": "xss.mark_safe_misuse",
        "confidence_score": 0.78,
    }),
    (re.compile(r"xss|cross.site.script", re.I), {
        "keyword": "XSS",
        "sub_category": "general",
        "concept_id": "xss",
        "mistake_type_concept_id": "xss.general",
        "confidence_score": 0.65,
    }),
    (re.compile(r"csrf_exempt|csrf.token|cross.site.request", re.I), {
        "keyword": "CSRF",
        "sub_category": "csrf_exempt_misuse",
        "concept_id": "csrf",
        "mistake_type_concept_id": "csrf.csrf_exempt_misuse",
        "confidence_score": 0.80,
    }),
    (re.compile(r"csrf", re.I), {
        "keyword": "CSRF",
        "sub_category": "general",
        "concept_id": "csrf",
        "mistake_type_concept_id": "csrf.general",
        "confidence_score": 0.60,
    }),
    (re.compile(r"login_required|permission.required|is_authenticated|@login", re.I), {
        "keyword": "AUTH_VULNERABILITY",
        "sub_category": "no_login_required",
        "concept_id": "auth_vulnerability",
        "mistake_type_concept_id": "auth_vulnerability.no_login_required",
        "confidence_score": 0.82,
    }),
    (re.compile(r"direct.object|insecure.*access|object.*permission", re.I), {
        "keyword": "AUTH_VULNERABILITY",
        "sub_category": "insecure_direct_object",
        "concept_id": "auth_vulnerability",
        "mistake_type_concept_id": "auth_vulnerability.insecure_direct_object",
        "confidence_score": 0.72,
    }),
    (re.compile(r"hardcoded.password|hardcoded.secret|hardcoded.credential", re.I), {
        "keyword": "AUTH_VULNERABILITY",
        "sub_category": "weak_password_policy",
        "concept_id": "auth_vulnerability",
        "mistake_type_concept_id": "auth_vulnerability.weak_password_policy",
        "confidence_score": 0.85,
    }),
]

_CONFIDENCE_THRESHOLD = 0.8


def _lookup_concept(rule_id: str, message: str) -> dict:
    """
    rule_id → RULE_CONCEPT_MAP 조회.
    없으면 message 패턴 매칭.
    둘 다 실패하면 빈 dict 반환.
    """
    # 1. rule_id 직접 매핑
    if rule_id in RULE_CONCEPT_MAP:
        return RULE_CONCEPT_MAP[rule_id].copy()

    # 2. message 패턴 매핑
    for pattern, mapping in _MESSAGE_PATTERNS:
        if pattern.search(message):
            result = mapping.copy()
            # confidence < 0.8 → sub_category를 "general"로 강등
            if result["confidence_score"] < _CONFIDENCE_THRESHOLD:
                result["sub_category"] = "general"
                result["mistake_type_concept_id"] = f"{result['concept_id']}.general"
            return result

    return {}


def extract_snippet(pr_diff: str, target_file: str, target_line: int) -> str:
    """
    pr_diff(unified diff 형식)에서 target_file의 target_line 추가 라인을 추출.

    unified diff 파싱:
        "+++ b/path/to/file" → 파일 섹션 시작
        "@@ -a,b +c,d @@"   → 현재 라인 번호 리셋 (c에서 시작)
        "+" 로 시작          → 추가 라인 (새 파일 기준 라인 번호 증가)
        "-" 로 시작          → 삭제 라인 (라인 번호 증가하지 않음)

    Returns:
        해당 라인의 코드 문자열 (앞 "+" 제거, 공백 trim).
        찾지 못하면 "snippet_unavailable" (빈 문자열 아님 — 요구사항 8).
    """
    if not pr_diff or not target_file:
        return "snippet_unavailable"

    # Windows 경로 정규화 — pylint은 'C:\..', bandit은 'C:/..'를 보고하므로
    # 구분자를 통일하지 않으면 경로 매칭이 실패해 snippet_unavailable이 된다.
    target_file = target_file.replace("\\", "/")
    in_target_file = False
    current_line = 0

    for raw_line in pr_diff.splitlines():
        # 파일 헤더: "+++ b/src/auth.py"
        if raw_line.startswith("+++ b/"):
            file_path = raw_line[6:].replace("\\", "/")
            # target_file이 경로 끝에 포함되는지 확인 (절대/상대 경로 모두 허용)
            in_target_file = (
                target_file == file_path
                or file_path.endswith(target_file)
                or target_file.endswith(file_path)
            )
            current_line = 0
            continue

        if not in_target_file:
            continue

        # Hunk 헤더: "@@ -3,7 +3,8 @@" → 새 파일 시작 라인 번호 추출
        hunk = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", raw_line)
        if hunk:
            current_line = int(hunk.group(1)) - 1  # 다음 라인에서 +1
            continue

        # "\ No newline at end of file" 등 메타 라인 무시
        if raw_line.startswith("\\"):
            continue

        if raw_line.startswith("-"):
            # 삭제 라인 → 새 파일 기준 라인 번호 증가 안 함
            continue

        if raw_line.startswith("+"):
            current_line += 1
            if current_line == target_line:
                return raw_line[1:].strip()  # 앞 "+" 제거
        else:
            # 컨텍스트 라인 (변경 없는 라인)
            current_line += 1
            if current_line == target_line:
                return raw_line.strip()

    return "snippet_unavailable"


# ── code_context 조립 (M4 개인화 피드백용) ───────────────────────────────────
# 이슈 라인 앞뒤로 추출할 컨텍스트 줄 수 (요구사항: 3~5줄)
_CONTEXT_LINES = 3

# concept → 규칙 기반 맥락 요약 (LLM 호출 없음)
_CONTEXT_SUMMARY_BY_CONCEPT: dict[str, str] = {
    "SQL Injection": "사용자 입력값이 SQL 문자열에 직접 결합되어 실행되는 코드 맥락입니다.",
    "XSS": "사용자 입력이 이스케이프 없이 HTML/템플릿에 출력되어 XSS가 발생할 수 있는 코드 맥락입니다.",
    "CSRF": "CSRF 보호가 누락되었거나 비활성화된 요청 처리 코드 맥락입니다.",
    "AUTH_VULNERABILITY": "인증·인가 검증이 누락되었을 수 있는 코드 맥락입니다.",
}


def _collect_file_lines(pr_diff: str, target_file: str) -> list[tuple[int, str]]:
    """
    unified diff에서 target_file의 (새 파일 라인번호, 코드) 목록을 추출.

    extract_snippet과 동일한 파싱 규칙을 쓰되, 단일 라인이 아니라
    파일 전체의 (추가 + 컨텍스트) 라인을 순서대로 수집한다.
    삭제(-) 라인은 새 파일 기준 라인 번호를 증가시키지 않으므로 제외한다.
    들여쓰기는 보존한다 (diff 마커 1글자만 제거).
    """
    if not pr_diff or not target_file:
        return []

    # Windows 경로 정규화 (extract_snippet과 동일 — 구분자 차이로 인한 매칭 실패 방지)
    target_file = target_file.replace("\\", "/")
    lines: list[tuple[int, str]] = []
    in_target_file = False
    current_line = 0

    for raw_line in pr_diff.splitlines():
        if raw_line.startswith("+++ b/"):
            file_path = raw_line[6:].replace("\\", "/")
            in_target_file = (
                target_file == file_path
                or file_path.endswith(target_file)
                or target_file.endswith(file_path)
            )
            current_line = 0
            continue

        if not in_target_file:
            continue

        hunk = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", raw_line)
        if hunk:
            current_line = int(hunk.group(1)) - 1
            continue

        if raw_line.startswith("\\"):  # "\ No newline at end of file"
            continue

        if raw_line.startswith("-"):   # 삭제 라인 → 라인 번호 증가 안 함
            continue

        if raw_line.startswith("+"):   # 추가 라인
            current_line += 1
            lines.append((current_line, raw_line[1:]))
        else:                          # 컨텍스트 라인 (앞 공백 마커 1글자 제거)
            current_line += 1
            lines.append((current_line, raw_line[1:] if raw_line else raw_line))

    return lines


# ── name_of_function 추출 (M4 개인화 피드백용) ────────────────────────────────
# 이슈 라인을 감싸는 함수명을 추출한다. Python은 AST로 정확히, 그 외 언어는
# 정규식으로 이슈 라인 위쪽을 역탐색한다. 함수 밖(모듈/클래스 본문)이면 "" 반환.

# 언어별 함수 정의 정규식 (정규식 fallback 경로에서 사용)
_FUNC_DEF_PATTERNS: dict[str, list[re.Pattern]] = {
    ".py": [re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)")],
    ".js": [
        re.compile(r"\bfunction\s+([A-Za-z_$][\w$]*)"),
        re.compile(r"\b([A-Za-z_$][\w$]*)\s*[:=]\s*(?:async\s*)?(?:function\b|\([^)]*\)\s*=>)"),
        re.compile(r"^\s*(?:async\s+)?([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{"),  # 메서드
    ],
    ".cs": [re.compile(r"\b(?:public|private|protected|internal|static|async|\s)+[\w<>\[\],\s]+\s+([A-Za-z_]\w*)\s*\(")],
}
# .jsx/.ts/.tsx는 .js 패턴 재사용
for _alias in (".jsx", ".ts", ".tsx"):
    _FUNC_DEF_PATTERNS[_alias] = _FUNC_DEF_PATTERNS[".js"]

_GENERIC_FUNC_PATTERNS = [re.compile(r"\b(?:def|function)\s+([A-Za-z_$][\w$]*)")]


def _py_enclosing_function(file_lines: list[tuple[int, str]], target_line: int) -> str | None:
    """
    Python AST로 target_line을 포함하는 가장 안쪽 함수명을 반환한다.

    파싱 성공 + 감싸는 함수 있음 → 함수명
    파싱 성공 + 함수 밖(모듈/클래스 본문) → "" (빈 문자열)
    파싱 실패(SyntaxError 등) → None (호출 측이 정규식 fallback으로 전환)
    """
    if not file_lines:
        return None

    max_ln = max(ln for ln, _ in file_lines)
    buf = [""] * (max_ln + 1)  # 1-indexed 복원용 (인덱스 0은 placeholder)
    for ln, txt in file_lines:
        if 0 < ln <= max_ln:
            buf[ln] = txt
    source = "\n".join(buf[1:])

    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None

    best: tuple[int, str] | None = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = node.lineno
            end = getattr(node, "end_lineno", start) or start
            if start <= target_line <= end:
                # 중첩 함수면 가장 안쪽(가장 큰 start) 선택
                if best is None or start > best[0]:
                    best = (start, node.name)
    return best[1] if best else ""


def _regex_enclosing_function(
    file_lines: list[tuple[int, str]], target_line: int, ext: str
) -> str:
    """이슈 라인 위쪽을 역탐색해 가장 가까운 함수 정의명을 찾는다 (비-Python/AST 실패용)."""
    by_line = {ln: txt for ln, txt in file_lines}
    patterns = _FUNC_DEF_PATTERNS.get(ext, _GENERIC_FUNC_PATTERNS)
    for ln in range(target_line, 0, -1):
        txt = by_line.get(ln)
        if txt is None:
            continue
        for pat in patterns:
            m = pat.search(txt)
            if m:
                return m.group(1)
    return ""


def extract_function_name(pr_diff: str, target_file: str, target_line: int) -> str:
    """
    이슈가 발생한 라인을 감싸는 함수명을 추출한다 (M4 개인화 피드백용).

    Python: AST로 target_line을 포함하는 가장 안쪽 함수를 정확히 찾는다.
    그 외 언어 또는 AST 파싱 실패: 정규식으로 라인 위쪽을 역탐색한다.
    함수 밖(모듈/클래스 본문)이거나 찾지 못하면 "" 반환.
    """
    if not pr_diff or not target_file:
        return ""

    file_lines = _collect_file_lines(pr_diff, target_file)
    if not file_lines:
        return ""

    ext = Path(target_file).suffix.lower()

    if ext == ".py":
        name = _py_enclosing_function(file_lines, target_line)
        if name is not None:
            return name  # 파싱 성공 — "" 도 유효 결과(함수 밖)

    return _regex_enclosing_function(file_lines, target_line, ext)


def _build_context_summary(keyword: str, message: str) -> str:
    """
    규칙 기반 맥락 요약 생성 (LLM 호출 없음).

    keyword 매핑이 있으면 사전 정의 문장을, 없으면 message 기반 문장을,
    둘 다 없으면 일반 문장을 반환한다. 절대 빈 문자열을 반환하지 않는다.
    """
    if keyword and keyword in _CONTEXT_SUMMARY_BY_CONCEPT:
        return _CONTEXT_SUMMARY_BY_CONCEPT[keyword]
    if message:
        return f"{message.strip()} — 정적 분석/보안 스캔에서 지적된 코드 맥락입니다."
    return "정적 분석/보안 스캔에서 지적된 코드 맥락입니다."


def build_code_context(
    pr_diff: str,
    target_file: str,
    target_line: int,
    code_snippet: str,
    keyword: str,
    message: str,
) -> dict:
    """
    이슈 라인 기준 앞뒤 코드 맥락을 조립한다 (M4 개인화 피드백용).

    생성 기준 (요구사항):
        - pr_diff / file / line / code_snippet 활용 (새 LLM 호출 없음)
        - 이슈 라인 앞뒤 _CONTEXT_LINES(3)줄 추출
        - diff에서 라인을 찾지 못하면 issue_line = code_snippet
        - code_snippet도 없으면 "snippet_unavailable"
        - context_summary는 규칙 기반으로 생성 (빈 문자열 금지)

    Returns:
        {"context_before": [...], "issue_line": str,
         "context_after": [...], "context_summary": str}
    """
    file_lines = _collect_file_lines(pr_diff, target_file)

    idx: int | None = None
    for k, (ln, _) in enumerate(file_lines):
        if ln == target_line:
            idx = k
            break

    if idx is not None:
        issue_line = file_lines[idx][1]
        before = [text for _, text in file_lines[max(0, idx - _CONTEXT_LINES):idx]]
        after = [text for _, text in file_lines[idx + 1:idx + 1 + _CONTEXT_LINES]]
    else:
        # diff에서 라인을 못 찾음 → code_snippet fallback
        issue_line = code_snippet if code_snippet else "snippet_unavailable"
        before, after = [], []

    return {
        "context_before": before,
        "issue_line": issue_line,
        "context_after": after,
        "context_summary": _build_context_summary(keyword, message),
    }


# ── taxonomy 분류 (M4 개인화 피드백용) ────────────────────────────────────────
# 성능/테스트/함수 정밀 분석은 M3 담당 → 보안/정적분석 분류만 생성한다.

_TAXONOMY_FALLBACK: dict[str, str] = {
    "category": "General",
    "subcategory": "Code Quality",
    "issue_type": "Unknown",
    "sub_issue_type": "General Review Issue",
}


def _detect(text: str, *needles: str) -> bool:
    """text(소문자 변환) 안에 needle 중 하나라도 있으면 True."""
    low = text.lower()
    return any(n.lower() in low for n in needles)


def build_taxonomy(
    rule_id: str,
    sub_category: str,
    message: str,
    code_snippet: str,
    issue_type: str,
    issue_line: str = "",
) -> dict:
    """
    보안/정적분석 기준 하위 분류를 규칙 기반으로 생성한다 (LLM 호출 없음).

    분류 규칙은 요구사항 명세를 그대로 따른다. 위에서부터 먼저 매칭되는 규칙을
    적용하며, 어느 것에도 해당하지 않으면 fallback을 반환한다.
    """
    rid = (rule_id or "").upper()
    text = f"{message}\n{code_snippet}\n{issue_line}"

    def tx(category: str, subcategory: str, itype: str, sub: str) -> dict:
        return {
            "category": category,
            "subcategory": subcategory,
            "issue_type": itype,
            "sub_issue_type": sub,
        }

    # ── SQL Injection ────────────────────────────────────────────────────────
    if rid == "B608" or sub_category == "raw_query":
        return tx("Security", "Injection", "SQL Injection", "Raw Query String Formatting")
    if sub_category == "no_parameterize":
        return tx("Security", "Injection", "SQL Injection", "Missing Parameterized Query")

    # ── XSS ──────────────────────────────────────────────────────────────────
    if _detect(text, "mark_safe") or sub_category == "mark_safe_misuse":
        return tx("Security", "XSS", "Cross-Site Scripting", "mark_safe Misuse")
    if _detect(text, "|safe", "| safe") or sub_category == "safe_filter_misuse":
        return tx("Security", "XSS", "Cross-Site Scripting", "Template Safe Filter Misuse")
    if _detect(text, "innerHTML") or sub_category == "inner_html_direct":
        return tx("Security", "XSS", "Cross-Site Scripting", "Direct innerHTML Assignment")

    # ── CSRF ─────────────────────────────────────────────────────────────────
    if _detect(text, "csrf_exempt") or sub_category == "csrf_exempt_misuse":
        return tx("Security", "CSRF", "Cross-Site Request Forgery", "csrf_exempt Misuse")
    if sub_category == "no_csrf_token":
        return tx("Security", "CSRF", "Cross-Site Request Forgery", "Missing CSRF Token")

    # ── 인증 / 인가 ───────────────────────────────────────────────────────────
    if sub_category == "no_login_required":
        return tx("Security", "Authentication & Authorization",
                  "Missing Authentication Check", "Missing login_required")
    if sub_category == "no_permission_check":
        return tx("Security", "Authentication & Authorization",
                  "Authorization Bypass", "Missing Object Permission Check")

    # ── 복잡도 (Radon / complexity) ───────────────────────────────────────────
    if _detect(message, "cyclomatic", "complexity") or "RADON" in rid or rid == "C901":
        return tx("Code Quality", "Complexity",
                  "Cyclomatic Complexity", "High Cyclomatic Complexity")

    # ── 일반 Pylint / ESLint lint ─────────────────────────────────────────────
    if issue_type == "Code Smell" or rule_id:
        return tx("Code Quality", "Maintainability", "Code Smell", "General Code Smell")

    # ── fallback ──────────────────────────────────────────────────────────────
    return dict(_TAXONOMY_FALLBACK)


def infer_learning_context(file: str, tech_stack: list[str]) -> LearningContext:
    """
    파일 확장자 + tech_stack으로 학습 컨텍스트 추론.

    언어: 파일 확장자 기반
    프레임워크: tech_stack 또는 파일 경로 내 키워드
    도메인: MVP 기본값 "ecommerce"
    """
    ext = Path(file).suffix.lower()
    tech_lower = [t.lower() for t in tech_stack]
    file_lower = file.lower()

    # 언어 추론
    language_map = {
        ".py": "python",
        ".js": "javascript", ".jsx": "javascript",
        ".ts": "typescript", ".tsx": "typescript",
        ".cs": "csharp",
        ".html": "html", ".htm": "html",
        ".css": "css", ".scss": "css",
    }
    language = language_map.get(ext, "unknown")

    # 프레임워크 추론
    if "django" in tech_lower or "django" in file_lower:
        framework = "django"
    elif "fastapi" in tech_lower or "fastapi" in file_lower:
        framework = "fastapi"
    elif "flask" in tech_lower or "flask" in file_lower:
        framework = "flask"
    elif "express" in tech_lower:
        framework = "express"
    elif language == "python":
        framework = "none"
    else:
        framework = "none"

    return LearningContext(
        framework=framework,
        language=language,
        domain_context="ecommerce",  # MVP 기본값
    )


def enrich_with_concept_mapping(
    issue: dict,
    pr_diff: str,
    tech_stack: list[str],
) -> dict:
    """
    단일 이슈 dict에 M4 매핑 필드를 추가하여 반환.

    concept 매핑 필드는 이미 concept이 채워져 있으면 덮어쓰지 않는다
    (LLM이 먼저 채운 경우 보존). 단, code_context / taxonomy 는 M4 개인화
    피드백용 구조화 정보이므로 항상 부여한다.

    Args:
        issue:     enriched 이슈 dict (llm_judge 결과)
        pr_diff:   PR unified diff 전체 문자열
        tech_stack: 개발자 기술 스택 목록

    Returns:
        M4 필드가 추가된 새 dict (원본 수정 안 함)
    """
    rule_id = issue.get("rule_id", "")
    message = issue.get("message", "")
    file = issue.get("file", "")
    line = issue.get("line", 0)
    issue_type = issue.get("issue_type", "")

    enriched = dict(issue)  # 원본 수정 방지

    # ── keyword 매핑 (이미 있으면 보존) ──────────────────────────────────────
    if not enriched.get("keyword"):
        mapping = _lookup_concept(rule_id, message)
        snippet = extract_snippet(pr_diff, file, line)
        if not snippet:
            snippet = "snippet_unavailable"
        enriched.update({
            "keyword":                 mapping.get("keyword", ""),
            "sub_category":            mapping.get("sub_category", ""),
            "concept_id":              mapping.get("concept_id", ""),
            "mistake_type_concept_id": mapping.get("mistake_type_concept_id", ""),
            "confidence_score":        mapping.get("confidence_score", 0.0),
            "code_snippet":            snippet,
            "learning_context":        infer_learning_context(file, tech_stack).model_dump(),
        })

    # 이후 단계에서 쓸 확정값 (keyword가 미리 있던 경우도 안전하게 조회)
    keyword = enriched.get("keyword", "")
    sub_category = enriched.get("sub_category", "")
    snippet = enriched.get("code_snippet") or extract_snippet(pr_diff, file, line)
    if not snippet:
        snippet = "snippet_unavailable"

    # ── code_context (M4 개인화 피드백용) ────────────────────────────────────
    enriched["code_context"] = build_code_context(
        pr_diff, file, line, snippet, keyword, message,
    )

    # ── taxonomy (M4 개인화 피드백용) ────────────────────────────────────────
    enriched["taxonomy"] = build_taxonomy(
        rule_id, sub_category, message, snippet, issue_type,
        enriched["code_context"]["issue_line"],
    )

    # ── name_of_function (M4 개인화 피드백용) ─────────────────────────────────
    # 이슈 라인을 감싸는 함수명. 함수 밖이면 "" 유지.
    enriched["name_of_function"] = extract_function_name(pr_diff, file, line)

    return enriched
