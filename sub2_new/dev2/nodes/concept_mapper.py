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

import re
from pathlib import Path

from dev2.schema import LearningContext

# ── rule_id 직접 매핑 ─────────────────────────────────────────────────────────
# Bandit / Semgrep / Pylint rule_id → concept 정보
RULE_CONCEPT_MAP: dict[str, dict] = {
    # SQL Injection
    "B608": {
        "concept": "SQL Injection",
        "mistake_type": "raw_query",
        "concept_id": "sql_injection",
        "mistake_type_concept_id": "sql_injection.raw_query",
        "confidence_score": 0.92,
    },
    "SEC-B608": {
        "concept": "SQL Injection",
        "mistake_type": "raw_query",
        "concept_id": "sql_injection",
        "mistake_type_concept_id": "sql_injection.raw_query",
        "confidence_score": 0.92,
    },
    # XSS
    "B703": {  # Django mark_safe
        "concept": "XSS",
        "mistake_type": "mark_safe_misuse",
        "concept_id": "xss",
        "mistake_type_concept_id": "xss.mark_safe_misuse",
        "confidence_score": 0.90,
    },
    "B308": {  # mark_safe
        "concept": "XSS",
        "mistake_type": "mark_safe_misuse",
        "concept_id": "xss",
        "mistake_type_concept_id": "xss.mark_safe_misuse",
        "confidence_score": 0.88,
    },
    # CSRF
    "B506": {
        "concept": "CSRF",
        "mistake_type": "csrf_exempt_misuse",
        "concept_id": "csrf",
        "mistake_type_concept_id": "csrf.csrf_exempt_misuse",
        "confidence_score": 0.88,
    },
    # 인증/인가
    "B105": {  # hardcoded password
        "concept": "AUTH_VULNERABILITY",
        "mistake_type": "hardcoded_credential",
        "concept_id": "auth_vulnerability",
        "mistake_type_concept_id": "auth_vulnerability.hardcoded_credential",
        "confidence_score": 0.95,
    },
    "B106": {
        "concept": "AUTH_VULNERABILITY",
        "mistake_type": "hardcoded_credential",
        "concept_id": "auth_vulnerability",
        "mistake_type_concept_id": "auth_vulnerability.hardcoded_credential",
        "confidence_score": 0.95,
    },
}

# ── message 패턴 매핑 (rule_id 미매핑 시 사용) ────────────────────────────────
# (compiled pattern, mapping dict) 리스트 — 순서대로 매칭
_MESSAGE_PATTERNS: list[tuple[re.Pattern, dict]] = [
    (re.compile(r"sql\s*inject|parameteriz|raw.query|string.format.*sql|%.*sql", re.I), {
        "concept": "SQL Injection",
        "mistake_type": "no_parameterize",
        "concept_id": "sql_injection",
        "mistake_type_concept_id": "sql_injection.no_parameterize",
        "confidence_score": 0.75,
    }),
    (re.compile(r"mark_safe|safe\s+filter|autoescape.*off|innerHTML|inner_html", re.I), {
        "concept": "XSS",
        "mistake_type": "mark_safe_misuse",
        "concept_id": "xss",
        "mistake_type_concept_id": "xss.mark_safe_misuse",
        "confidence_score": 0.78,
    }),
    (re.compile(r"xss|cross.site.script", re.I), {
        "concept": "XSS",
        "mistake_type": "general",
        "concept_id": "xss",
        "mistake_type_concept_id": "xss.general",
        "confidence_score": 0.65,
    }),
    (re.compile(r"csrf_exempt|csrf.token|cross.site.request", re.I), {
        "concept": "CSRF",
        "mistake_type": "csrf_exempt_misuse",
        "concept_id": "csrf",
        "mistake_type_concept_id": "csrf.csrf_exempt_misuse",
        "confidence_score": 0.80,
    }),
    (re.compile(r"csrf", re.I), {
        "concept": "CSRF",
        "mistake_type": "general",
        "concept_id": "csrf",
        "mistake_type_concept_id": "csrf.general",
        "confidence_score": 0.60,
    }),
    (re.compile(r"login_required|permission.required|is_authenticated|@login", re.I), {
        "concept": "AUTH_VULNERABILITY",
        "mistake_type": "no_login_required",
        "concept_id": "auth_vulnerability",
        "mistake_type_concept_id": "auth_vulnerability.no_login_required",
        "confidence_score": 0.82,
    }),
    (re.compile(r"direct.object|insecure.*access|object.*permission", re.I), {
        "concept": "AUTH_VULNERABILITY",
        "mistake_type": "insecure_direct_object",
        "concept_id": "auth_vulnerability",
        "mistake_type_concept_id": "auth_vulnerability.insecure_direct_object",
        "confidence_score": 0.72,
    }),
    (re.compile(r"hardcoded.password|hardcoded.secret|hardcoded.credential", re.I), {
        "concept": "AUTH_VULNERABILITY",
        "mistake_type": "hardcoded_credential",
        "concept_id": "auth_vulnerability",
        "mistake_type_concept_id": "auth_vulnerability.hardcoded_credential",
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
            # confidence < 0.8 → mistake_type을 "general"로 강등
            if result["confidence_score"] < _CONFIDENCE_THRESHOLD:
                result["mistake_type"] = "general"
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

    in_target_file = False
    current_line = 0

    for raw_line in pr_diff.splitlines():
        # 파일 헤더: "+++ b/src/auth.py"
        if raw_line.startswith("+++ b/"):
            file_path = raw_line[6:]
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

    이미 concept이 채워져 있으면 덮어쓰지 않는다 (LLM이 먼저 채운 경우 보존).

    Args:
        issue:     enriched 이슈 dict (llm_judge 결과)
        pr_diff:   PR unified diff 전체 문자열
        tech_stack: 개발자 기술 스택 목록

    Returns:
        M4 필드가 추가된 새 dict (원본 수정 안 함)
    """
    # 이미 concept이 있으면 스킵
    if issue.get("concept"):
        return issue

    rule_id = issue.get("rule_id", "")
    message = issue.get("message", "")
    file = issue.get("file", "")
    line = issue.get("line", 0)

    # concept 매핑
    mapping = _lookup_concept(rule_id, message)

    # code_snippet 추출
    snippet = extract_snippet(pr_diff, file, line)
    if not snippet:
        snippet = "snippet_unavailable"

    # learning_context 추론
    lc = infer_learning_context(file, tech_stack)

    return {
        **issue,
        "concept":                 mapping.get("concept", ""),
        "mistake_type":            mapping.get("mistake_type", ""),
        "concept_id":              mapping.get("concept_id", ""),
        "mistake_type_concept_id": mapping.get("mistake_type_concept_id", ""),
        "confidence_score":        mapping.get("confidence_score", 0.0),
        "code_snippet":            snippet,
        "learning_context":        lc,
    }
