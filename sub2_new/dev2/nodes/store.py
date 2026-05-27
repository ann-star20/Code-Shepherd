"""
store 노드 — PostgreSQL + BigQuery 이중 적재

이 노드는 llm_judge까지 완료된 enriched 이슈를 영구 저장소에 기록하고
Dev4 Aggregator가 소비할 final_output을 반환한다.

흐름:
    enriched (llm_judge 결과, _source 태깅 포함)
    → _source 기준 분리 ("static" / "security")
    → 에이전트별 AgentOutput 빌드 (Pydantic 검증 — 내부 필드 자동 제거)
    → PostgreSQL 적재 (scan_executions → scan_issues → scan_summaries)
    → BigQuery 적재 (analytics DW — 실패 시 로그만 남기고 스킵)
    → final_output 반환 (CLAUDE.md §5-A Output Contract)

OLTP vs OLAP 이중 적재 이유:
    PostgreSQL (OLTP): 운영 조회 (scan_id, PR별 이슈 상세) — 빠른 단건 조회
    BigQuery (OLAP):   analytics DW (에이전트별 정확도 추이, 개발자별 패턴 집계)
    → 두 저장소는 목적이 달라 동시에 유지한다.

_source 필드:
    vector_search 노드가 static_raw → _source="static",
    security_raw → _source="security" 로 태깅한다.
    store 노드는 이 태그를 보고 에이전트 이름을 결정한다.
      _source == "static"   → agent = "static_analysis"
      _source == "security" → agent = "security_scan"

Pydantic 경계 검증:
    Issue 모델에 정의된 필드(severity/line/file/message/rule_id/suggestion/similar_issues)만
    통과하고, llm_judged/llm_model/llm_rationale/_source 등 내부 필드는 자동 제거된다.
    → Dev4 Aggregator는 깨끗한 Output Contract만 받는다.

CLAUDE.md 준수:
    §3     trace_id: "pr_{12hex}" 형식
    §5-A   Output Contract: AgentOutput 필드 구조
    §10-4  PostgreSQL 실패 → re-raise (핵심 기능)
           BigQuery 실패 → 로그 + 스킵 (분석 부가 기능)
    §12    enriched 비어 있음 → 빈 리스트 반환 (예외 없음)
"""

import logging
import os
import time

# dev2.db는 모듈 로드 시 asyncpg(SQLAlchemy asyncpg 드라이버)를 import한다.
# asyncpg가 미설치된 환경(CI/개발)에서도 store.py를 import할 수 있도록
# db 함수들은 _persist() 내부에서 lazy import 한다. (CLAUDE.md §10-3 패턴)
from dev2.schema import AgentOutput, Dev2State, Issue, Summary

logger = logging.getLogger(__name__)

# ── BigQuery 설정 ─────────────────────────────────────────────────────────────
# BIGQUERY_PROJECT_ID 미설정 시 BigQuery 적재 전체 스킵 (개발 환경 기본값)
BIGQUERY_PROJECT_ID = os.getenv("BIGQUERY_PROJECT_ID", "")
BIGQUERY_DATASET = os.getenv("BIGQUERY_DATASET", "dev2_analytics")
BIGQUERY_TABLE = os.getenv("BIGQUERY_TABLE", "scan_results")

# Issue 모델의 유효 필드 목록 — 내부 필드(_source, llm_*) 필터링에 사용
_ISSUE_FIELDS = frozenset({
    "severity", "line", "file", "message", "rule_id", "suggestion", "similar_issues",
})


# ── 내부 헬퍼 ─────────────────────────────────────────────────────────────────

def _build_output(
    issues: list[dict],
    agent: str,
    task_id: str,
    exec_ms: int,
) -> dict:
    """
    이슈 목록을 AgentOutput Output Contract dict으로 변환한다.

    Pydantic 경계 검증:
        Issue 필드만 통과 (llm_judged/llm_model/llm_rationale/_source 제거).
        → Dev4는 깨끗한 Output Contract만 받는다 (CLAUDE.md §5-A).

    Args:
        issues: enriched + judged 이슈 목록 (내부 필드 포함 가능)
        agent:  "static_analysis" 또는 "security_scan"
        task_id: PR 단위 UUID
        exec_ms: 실행 시간 (milliseconds)

    Returns:
        AgentOutput.model_dump() — CLAUDE.md §5-A Output Contract dict
    """
    # ① _ISSUE_FIELDS만 남겨 내부 필드 제거 → Issue Pydantic 검증
    validated: list[Issue] = []
    for raw in issues:
        filtered = {k: v for k, v in raw.items() if k in _ISSUE_FIELDS}
        try:
            validated.append(Issue(**filtered))
        except Exception as exc:
            logger.warning(
                "_build_output: Issue 검증 실패 — %s | 이슈 제외 (rule_id=%s)",
                exc, raw.get("rule_id", "?"),
            )

    # ② Summary 계산
    summary = Summary(
        critical=sum(1 for i in validated if i.severity == "Critical"),
        major=sum(1 for i in validated if i.severity == "Major"),
        minor=sum(1 for i in validated if i.severity == "Minor"),
    )

    # ③ AgentOutput 빌드 → model_dump()로 dict 반환
    return AgentOutput(
        agent=agent,
        task_id=task_id,
        issues=validated,
        summary=summary,
        execution_ms=exec_ms,
    ).model_dump()


def _load_bigquery(output: dict, payload: dict) -> None:
    """
    BigQuery에 스캔 결과 집계 행을 적재한다.

    CLAUDE.md §10 패턴:
        BigQuery = analytics DW (부가 기능) → 실패 시 로그만 남기고 스킵.
        파이프라인 중단 없음.

    google.cloud.bigquery lazy import:
        google-cloud-bigquery 미설치 환경(개발/CI)에서 ModuleNotFoundError 방지.
        BIGQUERY_PROJECT_ID 미설정 시 함수 시작 시점에 조기 반환.

    Args:
        output:  AgentOutput dict (Output Contract)
        payload: PR 메타데이터 (task_id, pr_id, developer)
    """
    if not BIGQUERY_PROJECT_ID:
        logger.debug("_load_bigquery: BIGQUERY_PROJECT_ID 미설정 — BigQuery 적재 스킵")
        return

    try:
        # lazy import: google-cloud-bigquery가 없어도 모듈 로드 실패 없음
        from google.cloud import bigquery  # noqa: PLC0415

        client = bigquery.Client(project=BIGQUERY_PROJECT_ID)
        table_ref = f"{BIGQUERY_PROJECT_ID}.{BIGQUERY_DATASET}.{BIGQUERY_TABLE}"

        rows = [
            {
                "task_id": output["task_id"],
                "pr_id": payload.get("pr_id", ""),
                "developer_id": payload.get("developer", {}).get("id", ""),
                "agent": output["agent"],
                "critical": output["summary"]["critical"],
                "major": output["summary"]["major"],
                "minor": output["summary"]["minor"],
                "execution_ms": output["execution_ms"],
                "issue_count": len(output["issues"]),
            }
        ]

        errors = client.insert_rows_json(table_ref, rows)
        if errors:
            logger.warning("_load_bigquery: streaming insert 오류 — %s", errors)
        else:
            logger.info(
                "_load_bigquery: BigQuery 적재 완료 (agent=%s, table=%s)",
                output["agent"], table_ref,
            )

    except Exception as exc:
        # BigQuery 실패 = 스킵 (analytics 장애가 PR 리뷰를 막으면 안 됨)
        logger.error("_load_bigquery: 적재 실패 — %s | 스킵하고 계속 진행", exc)


async def _persist(
    output: dict,
    task_id: str,
    pr_id: str,
    developer_id: str,
    trace_id: str,
) -> None:
    """
    Cloud SQL (PostgreSQL)에 스캔 결과를 적재한다 (3-테이블 순차 INSERT).

    순서:
        1. scan_executions INSERT → scan_id 획득
        2. scan_issues INSERT (이슈별 행)
        3. scan_summaries UPSERT (재스캔 시 덮어쓰기)

    CLAUDE.md §10-4:
        PostgreSQL 실패 → re-raise. 핵심 기능이므로 삼키지 않는다.

    lazy import:
        dev2.db는 모듈 로드 시 asyncpg를 요구한다.
        미설치 환경에서 _persist 미호출 시 오류가 없도록 내부에서 import한다.

    Args:
        output:       AgentOutput dict
        task_id:      PR 처리 단위 UUID (Dev2State.task_id)
        pr_id:        GitHub PR 번호 (Dev2State.pr_id)
        developer_id: 개발자 ID (Dev2State.developer_id)
        trace_id:     CLAUDE.md §3 형식 ("pr_{12hex}")
    """
    # lazy import: asyncpg 미설치 환경에서 store.py 자체 import는 허용
    from dev2.db import insert_scan_execution, insert_scan_issues, insert_scan_summary  # noqa: PLC0415

    agent = output["agent"]
    execution_ms = output["execution_ms"]

    # ① scan_executions → scan_id
    scan_id = await insert_scan_execution(
        task_id=task_id,
        pr_id=pr_id,
        developer_id=developer_id,
        execution_ms=execution_ms,
        trace_id=trace_id,
    )
    logger.debug("_persist: scan_id=%d (agent=%s, trace_id=%s)", scan_id, agent, trace_id)

    # ② scan_issues (이슈별 행 INSERT)
    await insert_scan_issues(scan_id, output["issues"], agent)

    # ③ scan_summaries UPSERT
    await insert_scan_summary(scan_id, agent, output["summary"])

    logger.info(
        "_persist: PostgreSQL 적재 완료 (agent=%s, scan_id=%d, issues=%d)",
        agent, scan_id, len(output["issues"]),
    )


# ── trace_id 생성 ─────────────────────────────────────────────────────────────

def _make_trace_id(task_id: str) -> str:
    """
    CLAUDE.md §3 형식의 PR trace_id를 생성한다.

    task_id(UUID)의 하이픈을 제거한 후 처음 12자를 추출해
    "pr_{12hex}" 형태로 반환한다.

    Args:
        task_id: UUID 문자열 (하이픈 포함 가능)
                 예: "550e8400-e29b-41d4-a716-446655440000"

    Returns:
        "pr_550e8400e29b" 형식 (CLAUDE.md §3)
    """
    hex_part = task_id.replace("-", "")[:12]
    return f"pr_{hex_part}"


# ── LangGraph 노드 ────────────────────────────────────────────────────────────

async def store_node(state: Dev2State) -> dict:
    """
    LangGraph 노드: enriched 이슈를 PostgreSQL + BigQuery에 적재한다.

    흐름:
        1. enriched에서 _source 기준으로 static/security 이슈 분리
        2. 이슈 있는 에이전트별로 AgentOutput 빌드 (Pydantic 검증)
        3. PostgreSQL 적재 (_persist) — 실패 시 re-raise
        4. BigQuery 적재 (_load_bigquery) — 실패 시 스킵
        5. final_output 반환 (Dev4 입력)

    CLAUDE.md §5-A:
        final_output = [AgentOutput.model_dump(), ...]
        이슈가 없는 에이전트는 final_output에 포함하지 않는다.

    Args:
        state: Dev2State — payload, enriched 필드 사용

    Returns:
        {"final_output": [AgentOutput dict, ...]}
    """
    enriched: list[dict] = state.get("enriched", [])
    # Dev2State 필드를 직접 읽음 (scan.py의 _payload_to_state가 flat하게 저장)
    task_id: str = state.get("task_id", "unknown-task")
    pr_id: str = state.get("pr_id", "")
    developer_id: str = state.get("developer_id", "")
    trace_id = _make_trace_id(task_id)

    if not enriched:
        logger.warning("store_node: enriched 비어 있음 — final_output=[] 반환")
        return {"final_output": []}

    # ── _source 기준 분리 ──────────────────────────────────────────────────────
    static_issues = [i for i in enriched if i.get("_source") == "static"]
    security_issues = [i for i in enriched if i.get("_source") == "security"]

    # _source 미태깅 이슈 경고 (vector_search 노드 누락 시 발생)
    untagged = [i for i in enriched if "_source" not in i]
    if untagged:
        logger.warning(
            "store_node: _source 미태깅 이슈 %d개 감지 — vector_search 노드 확인 필요",
            len(untagged),
        )

    # 이슈가 있는 에이전트만 처리 (빈 에이전트는 final_output에 포함 안 함)
    agent_groups: list[tuple[str, list[dict]]] = []
    if static_issues:
        agent_groups.append(("static_analysis", static_issues))
    if security_issues:
        agent_groups.append(("security_scan", security_issues))

    # 실행 시간 근사치 (ms) — 실제 환경에서는 파이프라인 시작 시점 기록 필요
    exec_ms = int(time.monotonic() * 1000) % 100_000

    final_output: list[dict] = []

    for agent_name, issues in agent_groups:
        # ① AgentOutput 빌드 (Pydantic 검증 — 내부 필드 제거)
        output = _build_output(issues, agent_name, task_id, exec_ms)

        # ② Cloud SQL (PostgreSQL) 적재 (실패 시 re-raise)
        try:
            await _persist(output, task_id, pr_id, developer_id, trace_id)
        except Exception as exc:
            logger.error(
                "store_node: PostgreSQL 적재 실패 (agent=%s) — %s",
                agent_name, exc,
            )
            raise  # CLAUDE.md §10-4: 핵심 기능 실패는 상위로 전파

        # ③ BigQuery 적재 (실패 시 스킵)
        try:
            _load_bigquery(output, payload)
        except Exception as exc:
            # _load_bigquery 내부에서 이미 처리하지만, 누출 예외도 여기서 흡수
            logger.error(
                "store_node: _load_bigquery 예외 누출 (agent=%s) — %s | 스킵",
                agent_name, exc,
            )

        final_output.append(output)

    logger.info(
        "store_node 완료: final_output %d개 (static=%d, security=%d, trace=%s)",
        len(final_output), len(static_issues), len(security_issues), trace_id,
    )

    return {"final_output": final_output}
