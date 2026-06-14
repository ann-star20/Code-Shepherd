"""review_issue DB 어댑터 — GCP Cloud SQL (PostgreSQL) 또는 SQLite mock.

ENABLE_DB_WRITE=true 일 때만 INSERT 실행 (기본 false — eval·개발 중 INSERT 금지).
연결 우선순위: DB_HOST/PORT/NAME/USER/PASSWORD > POSTGRES_URL
그 외 → SQLite mock (tests/.dev3_mock.db).

INSERT 실패해도 파이프라인 중단 금지 — 로깅 후 continue.
키 값을 로그에 절대 출력하지 않는다.
"""
from __future__ import annotations

import logging
import os
import re
import sqlite3
from pathlib import Path

from contracts import Finding

log = logging.getLogger(__name__)

_MOCK_DB_PATH = Path(__file__).parent.parent.parent / "tests" / ".dev3_mock.db"

# ── 설정 ────────────────────────────────────────────────────────────────────

_SEVERITY_MAP: dict[str, str] = {
    "Major": "medium",
    "Minor": "low",
    "Info": "low",
    "Critical": "critical",
}

# (keyword(한글), sub_category(영문 이슈명)) — 팀 표준 형식
_RULE_MAP: dict[str, tuple[str, str]] = {
    "CONV-API-001": ("동기 HTTP 호출",       "Async Sync HTTP Call - Event Loop Blocking"),
    "CONV-TIME-002": ("타임존 불일치",        "Timezone Mismatch - Non-Standard Datetime"),
    "CONV-LOG-003": ("비구조적 로깅",        "Unstructured Logging - Missing Structured Logger"),
    "CONV-DB-004": ("N+1 쿼리",             "N+1 Query - Database Loop Call"),
    "CONV-DEP-005": ("금지 의존성",          "Prohibited Dependency - Unapproved Library"),
    "CONV-ERR-006": ("예외 무음 처리",       "Silent Exception - Missing Error Reporting"),
    "CONV-CFG-007": ("환경변수 직접 접근",   "Config Access - Direct Env Variable Usage"),
    "CONV-SQL-008": ("SQL Injection",        "cursor.execute() 오용 — 주문 내역 조회"),
}

# backward-compat: test_all_8_rules_in_keyword_map
_KEYWORD_MAP: dict[str, str] = {k: v[0] for k, v in _RULE_MAP.items()}

_SUGGESTION_MAP: dict[str, str] = {
    "CONV-API-001": "[CONV-API-001] async 함수 내에서는 httpx.AsyncClient 를 사용하세요. requests 동기 호출은 이벤트루프를 블로킹합니다.",
    "CONV-TIME-002": "[CONV-TIME-002] datetime.now()/utcnow() 대신 common.timeutil.now() 를 사용하세요. TZ 불일치를 방지합니다.",
    "CONV-LOG-003": "[CONV-LOG-003] print()/f-string 로깅 대신 struct_logger.log(event=...) 를 사용하세요. PII 마스킹 필터가 구조적 로거에만 적용됩니다.",
    "CONV-DB-004": "[CONV-DB-004] 루프 내 ORM/쿼리 호출을 일괄 조회(bulk fetch)로 변경하세요.",
    "CONV-DEP-005": "[CONV-DEP-005] lodash 대신 사내 ts-stdlib 를 사용하세요.",
    "CONV-ERR-006": "[CONV-ERR-006] bare except/pass 대신 errors.report(err_code=...) 를 사용하세요.",
    "CONV-CFG-007": "[CONV-CFG-007] os.getenv() 직접 호출 대신 config.from_env() 검증 로더를 사용하세요.",
    "CONV-SQL-008": "[CONV-SQL-008] f-string SQL 조립 대신 파라미터 바인딩(%s 또는 ?)을 사용하세요.",
}

_PLACEHOLDER_MARKERS = ("password@host", "@host:", "user:password", "YOUR_PASSWORD",
                        "://user:****@host", "@host:5432/dbname")

_MOCK_SCHEMA = """
CREATE TABLE IF NOT EXISTS review_issue (
    id                   TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    pull_request_id      TEXT,
    user_id              TEXT,
    github_id            TEXT,
    agent                TEXT,
    severity             TEXT,
    keyword              TEXT,
    sub_category         TEXT,
    code_context         TEXT,
    code_snippet         TEXT,
    suggestion           TEXT,
    programming_language TEXT,
    framework            TEXT,
    framework_version    TEXT,
    name_of_function     TEXT,
    created_at           TEXT DEFAULT (datetime('now'))
);
"""

# diff에서 def 추출용 패턴
_DEF_RE = re.compile(r"^[+ ]?\s*(?:async\s+)?def\s+(\w+)\s*\(")
_HUNK_DEF_RE = re.compile(r"^@@.*?@@\s+(?:async\s+)?def\s+(\w+)")


# ── 연결 ─────────────────────────────────────────────────────────────────────

def _pg_dsn_kwargs() -> dict | None:
    """DB_HOST 기반 DSN 우선, 없으면 POSTGRES_URL 시도. 실패하면 None."""
    host = os.getenv("DB_HOST", "")
    if host:
        return {
            "host": host,
            "port": int(os.getenv("DB_PORT", "5432")),
            "dbname": os.getenv("DB_NAME", ""),
            "user": os.getenv("DB_USER", ""),
            "password": os.getenv("DB_PASSWORD", ""),
            "sslmode": "require",
        }
    url = os.getenv("POSTGRES_URL", "")
    if url and not any(m in url for m in _PLACEHOLDER_MARKERS):
        return {"dsn": url}
    return None


def check_pg_connection() -> tuple[bool, str]:
    """DB 연결 유효성 + SELECT 1 테스트. (값을 로그에 출력하지 않는다.)"""
    kwargs = _pg_dsn_kwargs()
    if kwargs is None:
        return False, "DB connection not configured (set DB_HOST or valid POSTGRES_URL)"
    try:
        import psycopg2  # noqa: PLC0415
        conn = psycopg2.connect(connect_timeout=5, **kwargs)
        cur = conn.cursor()
        cur.execute("SELECT 1")
        conn.close()
        return True, "OK"
    except ImportError:
        return False, "psycopg2 not installed — add psycopg2-binary to requirements.txt"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: (connection details redacted)"


def _is_real_db_available() -> bool:
    ok, _ = check_pg_connection()
    return ok


# ── 코드 추출 헬퍼 ────────────────────────────────────────────────────────────

def _code_snippet(evidence_lines: list[str]) -> str:
    """evidence_lines에서 +/- 접두 제거 → 순수 코드."""
    return "\n".join(
        line[1:] if line and line[0] in "+-" else line
        for line in evidence_lines
    )


def _name_of_function(evidence_lines: list[str], diff: str = "") -> str | None:
    """위반 라인이 속한 함수명 추출. evidence → diff 컨텍스트 순으로 시도."""
    # 1. evidence_lines에 직접 def 선언이 있는 경우 (새로 추가된 함수)
    for line in evidence_lines:
        m = _DEF_RE.match(line)
        if m:
            return m.group(1)

    if not diff:
        return None

    # 2. diff 전체 스캔: 첫 번째 evidence 라인 직전의 마지막 def
    evidence_set = set(evidence_lines)
    last_def: str | None = None
    for line in diff.splitlines():
        hunk_m = _HUNK_DEF_RE.match(line)
        if hunk_m:
            last_def = hunk_m.group(1)
            continue
        def_m = _DEF_RE.match(line)
        if def_m:
            last_def = def_m.group(1)
            continue
        if line in evidence_set:
            return last_def

    return last_def


# ── 행 값 빌더 ───────────────────────────────────────────────────────────────

def _build_row(finding: Finding, pr_number: int, repository: str,
               github_id: str | None, diff: str = "") -> dict:
    evidence = finding.evidence_lines or []
    keyword, sub_cat = _RULE_MAP.get(finding.rule_id, (finding.rule_id, finding.rule_id))
    return {
        "github_id": github_id,
        "agent": "dev3",
        "severity": _SEVERITY_MAP.get(finding.severity, finding.severity.lower()),
        "keyword": keyword,
        "sub_category": sub_cat,
        "code_context": "\n".join(evidence),
        "code_snippet": _code_snippet(evidence),
        "suggestion": _SUGGESTION_MAP.get(finding.rule_id, finding.rule_quote or ""),
        "programming_language": "python",
        "framework": None,
        "framework_version": None,
        "name_of_function": _name_of_function(evidence, diff),
    }


# ── SQLite mock ──────────────────────────────────────────────────────────────

def _mock_conn(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or _MOCK_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.executescript(_MOCK_SCHEMA)
    return conn


def _mock_insert(row: dict, pr_number: int, repository: str,
                 db_path: Path | None = None) -> None:
    conn = _mock_conn(db_path)
    try:
        conn.execute(
            """INSERT INTO review_issue
               (github_id, agent, severity, keyword, sub_category,
                code_context, code_snippet, suggestion, programming_language,
                framework, framework_version, name_of_function)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                row["github_id"], row["agent"], row["severity"],
                row["keyword"], row["sub_category"], row["code_context"],
                row["code_snippet"], row["suggestion"], row["programming_language"],
                row["framework"], row["framework_version"], row["name_of_function"],
            ),
        )
        conn.commit()
    finally:
        conn.close()


# ── GCP PostgreSQL ────────────────────────────────────────────────────────────

def _pg_insert(row: dict, pr_number: int, repository: str) -> None:
    import psycopg2  # noqa: PLC0415

    kwargs = _pg_dsn_kwargs()
    if kwargs is None:
        raise RuntimeError("DB connection not configured")

    conn = psycopg2.connect(connect_timeout=10, **kwargs)
    try:
        with conn.cursor() as cur:
            # 1. pull_request_id + user_id: pull_requests 서브쿼리
            cur.execute(
                "SELECT id, user_id FROM pull_requests "
                "WHERE github_pr_number = %s AND repository_full_name = %s LIMIT 1",
                (pr_number, repository),
            )
            pr_row = cur.fetchone()
            pull_request_id = str(pr_row[0]) if pr_row else None
            user_id = str(pr_row[1]) if pr_row else None

            # 2. user_id 없으면 github_id → users 테이블로 보완
            if user_id is None and row.get("github_id"):
                cur.execute(
                    "SELECT user_id FROM users WHERE github_id = %s LIMIT 1",
                    (row["github_id"],),
                )
                u_row = cur.fetchone()
                user_id = str(u_row[0]) if u_row else None

            cur.execute(
                "INSERT INTO review_issue "
                "(pull_request_id, user_id, github_id, agent, severity, keyword, sub_category, "
                "code_context, code_snippet, suggestion, programming_language, "
                "framework, framework_version, name_of_function) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    pull_request_id, user_id,
                    row["github_id"], row["agent"], row["severity"],
                    row["keyword"], row["sub_category"], row["code_context"],
                    row["code_snippet"], row["suggestion"], row["programming_language"],
                    row["framework"], row["framework_version"], row["name_of_function"],
                ),
            )
        conn.commit()
    finally:
        conn.close()


# ── 공개 API ─────────────────────────────────────────────────────────────────

def insert_review_issues(
    findings: list[Finding],
    pr_number: int,
    repository: str,
    github_id: str | None = None,
    diff: str = "",
    _mock_db_path: Path | None = None,
) -> None:
    """violation findings → review_issue INSERT. ENABLE_DB_WRITE=false면 no-op.

    INSERT 실패해도 파이프라인 중단 금지 (예외 삼킴, 로그만).
    """
    if os.getenv("ENABLE_DB_WRITE", "false").lower() != "true":
        return

    use_real = _is_real_db_available()
    for finding in findings:
        if finding.verdict != "violation":
            continue
        row = _build_row(finding, pr_number, repository, github_id, diff)
        try:
            if use_real:
                _pg_insert(row, pr_number, repository)
            else:
                _mock_insert(row, pr_number, repository, _mock_db_path)
            log.info("db_adapter: inserted rule_id=%s pr=%s repo=%s",
                     finding.rule_id, pr_number, repository)
        except Exception as exc:  # noqa: BLE001 — INSERT 실패 시 파이프라인 계속
            log.warning("db_adapter: insert failed rule_id=%s: %s",
                        finding.rule_id, type(exc).__name__)
