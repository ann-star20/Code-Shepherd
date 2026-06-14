import json
import os
import ssl
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# Cloud SQL (PostgreSQL) 연결
# 로컬 개발: Cloud SQL Auth Proxy 사용 (localhost:5432)
# Cloud Run / GCE: unix socket 경로 사용
#
# 로컬 proxy 예시:
#   DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/dev2_db
#
# Cloud Run 예시:
#   DATABASE_URL=postgresql+asyncpg://user:password@/dev2_db?host=/cloudsql/project:region:instance
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://user:password@localhost:5432/dev2_db"
)

# [CLAUDE.md §6] 자격증명이 포함된 DATABASE_URL을 stdout에 출력하지 않는다.
# [CLAUDE.md §10-3] Lazy 초기화 패턴
# asyncpg 미설치 환경(CI/테스트)에서 db.py import 시 에러가 나지 않도록
# create_async_engine + sessionmaker를 최초 사용 시점까지 지연한다.
_engine = None
_session_factory = None


def _get_engine():
    global _engine
    if _engine is None:
        # asyncpg는 sslmode를 지원하지 않으므로 localhost가 아닌 경우 connect_args로 SSL 활성화
        # Cloud SQL은 자체 인증서를 사용하므로 verify_mode=CERT_NONE으로 설정
        is_remote = "localhost" not in DATABASE_URL and "127.0.0.1" not in DATABASE_URL
        if is_remote:
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            connect_args = {"ssl": ssl_ctx}
        else:
            connect_args = {}
        _engine = create_async_engine(
            DATABASE_URL,
            pool_pre_ping=True,
            pool_recycle=60,
            pool_size=1,
            max_overflow=0,
            connect_args=connect_args,
        )
    return _engine


def _get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=_get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


def _safe_db_value(v, default=""):
    if v is None:
        return default
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return v


def AsyncSessionLocal():
    """
    AsyncSession 컨텍스트 매니저를 반환한다.

    사용 패턴:
        async with AsyncSessionLocal() as s:
            await s.execute(...)

    최초 호출 시 asyncpg 엔진을 lazy 초기화한다.
    테스트에서 patch("dev2.db.AsyncSessionLocal")으로 교체 가능.
    """
    return _get_session_factory()()


async def insert_scan_execution(
    task_id: str,
    pr_id: str,
    execution_ms: int,
    developer_id: str | None = None,
    trace_id: str | None = None,
) -> int:
    """scan_executions에 스캔 실행 기록을 INSERT하고 생성된 id를 반환한다."""
    async with AsyncSessionLocal() as s:
        r = await s.execute(text("""
            INSERT INTO scan_executions (task_id, pr_id, execution_ms, user_id)
            VALUES (
                :task_id, :pr_id, :execution_ms,
                (SELECT user_id FROM users WHERE github_id = :github_id LIMIT 1)
            )
            RETURNING id
        """), {
            "task_id": task_id,
            "pr_id": pr_id,
            "execution_ms": execution_ms,
            "github_id": developer_id,
        })
        await s.commit()
        return r.scalar()


async def insert_scan_issues(scan_id: int, issues: list[dict], agent: str):
    if not issues:
        return

    async with AsyncSessionLocal() as s:
        for i in issues:
            params = {
                "scan_id": scan_id,
                "agent": agent,
                "severity": i["severity"],
                "rule_id": i["rule_id"],
                "file": i.get("file", ""),
                "line": i.get("line", 0),
                "message": i["message"],
                "suggestion": i.get("suggestion", ""),
                "similar_issues": _safe_db_value(i.get("similar_issues"), "[]"),
                "issue_type": i.get("issue_type", ""),
                "resolution_example": i.get("resolution_example", ""),
                "status": i.get("status", "Open"),
                "keyword": i.get("keyword", ""),
                "sub_keyword": i.get("sub_keyword", ""),
                "metric_value": i.get("metric_value", ""),
                "sub_category": i.get("sub_category", ""),
                "concept_id": i.get("concept_id", ""),
                "mistake_type_concept_id": i.get("mistake_type_concept_id", ""),
                "confidence_score": i.get("confidence_score", 0.0),
                "code_snippet": i.get("code_snippet", ""),
                "learning_context": _safe_db_value(i.get("learning_context"), "{}"),
                "code_context": _safe_db_value(i.get("code_context"), "{}"),
                "taxonomy": _safe_db_value(i.get("taxonomy"), "{}"),
            }

            await s.execute(text("""
                INSERT INTO scan_issues
                  (scan_id, agent, severity, rule_id, file, line, message, suggestion,
                   similar_issues, issue_type, resolution_example, status,
                   keyword, sub_keyword, metric_value, sub_category,
                   concept_id, mistake_type_concept_id,
                   confidence_score, code_snippet,
                   learning_context, code_context, taxonomy)
                VALUES
                  (:scan_id, :agent, :severity, :rule_id, :file, :line, :message, :suggestion,
                   :similar_issues, :issue_type, :resolution_example, :status,
                   :keyword, :sub_keyword, :metric_value, :sub_category,
                   :concept_id, :mistake_type_concept_id,
                   :confidence_score, :code_snippet,
                   :learning_context, :code_context, :taxonomy)
            """), params)

        await s.commit()


# severity 매핑: scan_issues(Critical/Major/Minor) → review_issue(critical/high/medium)
_REVIEW_SEVERITY_MAP: dict[str, str] = {
    "Critical": "critical",
    "Major":    "high",
    "Minor":    "medium",
}


async def _lookup_pull_request_id(pr_id: str) -> str | None:
    """pull_requests.github_pr_number로 pull_requests.id(uuid)를 조회한다.
    찾지 못하면 None 반환 (review_issue.pull_request_id는 nullable).
    """
    try:
        pr_number = int(pr_id)
    except (ValueError, TypeError):
        return None
    async with AsyncSessionLocal() as s:
        r = await s.execute(
            text("SELECT id FROM pull_requests WHERE github_pr_number = :n LIMIT 1"),
            {"n": pr_number},
        )
        row = r.scalar()
        return str(row) if row else None


async def insert_review_issues(
    issues: list[dict],
    agent: str,
    pr_id: str,
    user_id: str | None,
    tech_stack: list[str],
) -> None:
    """review_issue 테이블에 이슈별 행을 INSERT한다.

    scan_issues와 달리 pull_request_id(uuid), programming_language, framework,
    name_of_function 컬럼을 사용하며, severity는 critical/high/medium 체계를 따른다.

    Args:
        issues:     enriched 이슈 목록
        agent:      'static_analysis' | 'security_scan'
        pr_id:      GitHub PR 번호 (pull_requests 조회에 사용)
        user_id:    개발자 UUID
        tech_stack: 개발자 기술 스택 (예: ["python", "fastapi"])
    """
    if not issues:
        return

    pull_request_id = await _lookup_pull_request_id(pr_id)
    programming_language = tech_stack[0] if tech_stack else ""
    framework = tech_stack[1] if len(tech_stack) > 1 else ""

    async with AsyncSessionLocal() as s:
        for i in issues:
            severity_raw = i.get("severity", "Minor")
            severity = _REVIEW_SEVERITY_MAP.get(severity_raw, "medium")
            await s.execute(text("""
                INSERT INTO review_issue
                  (pull_request_id, user_id, github_id, agent, severity,
                   keyword, sub_category, code_context, code_snippet,
                   suggestion, programming_language, framework,
                   name_of_function)
                VALUES
                  (:pull_request_id, :user_id, :github_id, :agent, :severity,
                   :keyword, :sub_category, :code_context, :code_snippet,
                   :suggestion, :programming_language, :framework,
                   :name_of_function)
            """), {
                "pull_request_id":      pull_request_id,
                "user_id":              user_id,
                "github_id":            pr_id,
                "agent":                agent,
                "severity":             severity,
                "keyword":              i.get("keyword") or i.get("rule_id", ""),
                "sub_category":         i.get("sub_category", ""),
                "code_context":         _safe_db_value(i.get("code_context"), ""),
                "code_snippet":         i.get("code_snippet", ""),
                "suggestion":           i.get("suggestion", ""),
                "programming_language": programming_language,
                "framework":            framework,
                "name_of_function":     i.get("name_of_function", ""),
            })
        await s.commit()


async def insert_aggregated_result(
    task_id: str,
    pr_id: str,
    developer_id: str,
    issues: list[dict],
    summary: dict,
) -> None:
    """aggregate_node 결과를 scan_executions + scan_issues + scan_summaries에 한 번에 적재한다."""
    scan_id = await insert_scan_execution(task_id, pr_id, execution_ms=0, developer_id=developer_id)
    if issues:
        agent = issues[0].get("agent", "static_analysis")
        await insert_scan_issues(scan_id, issues, agent)
    await insert_scan_summary(scan_id, summary.get("agent", "static_analysis"), {
        "critical": summary.get("critical", 0),
        "major":    summary.get("major", 0),
        "minor":    summary.get("minor", 0),
    })


def _jload(value, default):
    """JSONB 컬럼을 파싱한다. 드라이버가 dict/list로 이미 디코드했으면 그대로,
    문자열이면 json.loads, 그 외/실패면 default를 반환한다."""
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


async def fetch_scan_results_by_task(task_id: str) -> list[dict]:
    """
    task_id로 적재된 스캔 결과를 Dev4 입력(all_results) 형태로 복원한다 (DB 릴레이).

    Dev2/Dev3가 scan_executions / scan_issues / scan_summaries에 저장한 데이터를
    agent별 AgentOutput dict 리스트로 재구성한다. 이슈가 없는(clean) 에이전트는
    집계에 기여하지 않으므로 결과에서 생략한다.

    Returns:
        [{"agent", "task_id", "issues": [...], "summary": {...}, "execution_ms"}, ...]
        해당 task_id의 적재 결과가 없으면 빈 리스트.
    """
    async with AsyncSessionLocal() as s:
        issue_rows = (await s.execute(text("""
            SELECT se.execution_ms,
                   si.agent, si.severity, si.rule_id, si.file, si.line,
                   si.message, si.suggestion, si.similar_issues, si.issue_type,
                   si.resolution_example, si.status, si.keyword, si.sub_category,
                   si.concept_id, si.mistake_type_concept_id, si.confidence_score,
                   si.code_snippet, si.sub_keyword, si.metric_value,
                   si.learning_context, si.code_context, si.taxonomy
            FROM scan_executions se
            JOIN scan_issues si ON si.scan_id = se.id
            WHERE se.task_id = :task_id
            ORDER BY se.id
        """), {"task_id": task_id})).mappings().all()

        summary_rows = (await s.execute(text("""
            SELECT ss.agent, ss.critical, ss.major, ss.minor
            FROM scan_summaries ss
            JOIN scan_executions se ON ss.scan_id = se.id
            WHERE se.task_id = :task_id
        """), {"task_id": task_id})).mappings().all()

    by_agent: dict[str, dict] = {}
    for r in issue_rows:
        bucket = by_agent.setdefault(r["agent"], {
            "agent":        r["agent"],
            "task_id":      task_id,
            "issues":       [],
            "summary":      {"critical": 0, "major": 0, "minor": 0},
            "execution_ms": r["execution_ms"] or 0,
        })
        bucket["issues"].append({
            "severity":                r["severity"],
            "line":                    r["line"],
            "file":                    r["file"],
            "message":                 r["message"],
            "rule_id":                 r["rule_id"],
            "suggestion":              r["suggestion"],
            "issue_type":              r["issue_type"] or "Bug",
            "resolution_example":      r["resolution_example"] or "",
            "status":                  r["status"] or "Open",
            "similar_issues":          _jload(r["similar_issues"], []),
            "keyword":                 r["keyword"] or "",
            "sub_category":            r["sub_category"] or "",
            "concept_id":              r["concept_id"] or "",
            "mistake_type_concept_id": r["mistake_type_concept_id"] or "",
            "confidence_score":        r["confidence_score"] or 0.0,
            "code_snippet":            r["code_snippet"] or "",
            "sub_keyword":             r["sub_keyword"] or "",
            "metric_value":            r["metric_value"] or "",
            "learning_context":        _jload(r["learning_context"], {}),
            "code_context":            _jload(r["code_context"], {}),
            "taxonomy":                _jload(r["taxonomy"], {}),
        })

    # 집계 테이블 값으로 summary 덮어쓰기 (scan_summaries가 정확한 집계)
    for sr in summary_rows:
        if sr["agent"] in by_agent:
            by_agent[sr["agent"]]["summary"] = {
                "critical": sr["critical"] or 0,
                "major":    sr["major"] or 0,
                "minor":    sr["minor"] or 0,
            }

    return list(by_agent.values())


async def insert_scan_summary(scan_id: int, agent: str, summary: dict):
    async with AsyncSessionLocal() as s:
        # UPSERT: 재스캔 시 덮어쓰기 (uq_scan_summaries_scan_agent 활용)
        await s.execute(text("""
            INSERT INTO scan_summaries (scan_id, agent, critical, major, minor)
            VALUES (:scan_id, :agent, :critical, :major, :minor)
            ON CONFLICT (scan_id, agent)
            DO UPDATE SET
                critical = EXCLUDED.critical,
                major    = EXCLUDED.major,
                minor    = EXCLUDED.minor
        """), {"scan_id": scan_id, "agent": agent, **summary})
        await s.commit()
