"""
insights.py — GET /insights/* 엔드포인트 (분석 통계 조회 API)

Analytics 읽기 전용 라우터. scan_executions / scan_issues / scan_summaries 테이블에서
개발자별·팀별·시계열 집계 데이터를 반환한다.

엔드포인트:
    GET /insights/developer/{developer_id}  개발자 개인 이슈 통계
    GET /insights/team                      팀 이번달 Top 5 이슈
    GET /insights/trends                    주간 Critical 추이

OLAP 읽기 원칙:
    - PostgreSQL에서 집계 (OLTP 읽기). 대용량 장기 분석은 BigQuery(OLAP)를 사용.
    - 모든 쿼리는 파라미터 바인딩 (`:param` 형식) — SQL 인젝션 방지 (CLAUDE.md §6)
    - SELECT만 수행 → side effect 없음 → HTTP GET 사용

오류 처리:
    DB 연결 실패 → 빈 결과 반환 (로그만 남김).
    analytics 조회 실패가 서비스 전체를 막으면 안 됨.
    (vs store 노드 PostgreSQL 실패 → re-raise — CLAUDE.md §10-4)
"""

import logging

from fastapi import APIRouter
from sqlalchemy import text

# [CLAUDE.md §10-3] lazy import 패턴:
# dev2.db는 모듈 로드 시 asyncpg(create_async_engine)를 요구한다.
# asyncpg 미설치 환경(CI/테스트)에서 insights.py 자체 import를 허용하려면
# AsyncSessionLocal을 모듈 레벨이 아닌 함수 내부에서 import해야 한다.
# 각 엔드포인트 함수 상단의 `from dev2.db import AsyncSessionLocal`이 이 역할을 한다.

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("/developer/{developer_id}")
async def get_developer_insights(developer_id: str):
    """
    개발자 개인 이슈 통계 조회.

    scan_issues + scan_executions JOIN으로 해당 개발자의 rule_id별 이슈 빈도를 반환.
    Dev5 커리큘럼 생성, Dev4 개인화 피드백에 사용.

    SQL 설계:
        rule_id + severity 기준 GROUP BY → 반복 패턴 식별
        COUNT DESC 정렬 → 빈발 이슈 우선 (학습 우선순위)

    Args:
        developer_id: URL 경로 파라미터 (예: "dev-001")

    Returns:
        {"developer_id": str, "issues": [{"rule_id": ..., "severity": ..., "count": ...}, ...]}
    """
    try:
        from dev2.db import AsyncSessionLocal  # noqa: PLC0415 — lazy import (asyncpg 없는 테스트 환경 대비)
        async with AsyncSessionLocal() as s:
            r = await s.execute(
                text("""
                    SELECT si.rule_id, si.severity, COUNT(*) as count
                    FROM scan_issues si
                    JOIN scan_executions se ON si.scan_id = se.id
                    WHERE se.developer_id = :did
                    GROUP BY si.rule_id, si.severity
                    ORDER BY count DESC
                """),
                {"did": developer_id},  # 파라미터 바인딩 — SQL 인젝션 방지
            )
            issues = [dict(row) for row in r.mappings().all()]
    except Exception as exc:
        # analytics 조회 실패 → 빈 결과 반환 (핵심 기능 아님)
        logger.warning(
            "get_developer_insights: DB 조회 실패 (developer_id=%s) — %s | 빈 결과 반환",
            developer_id, exc,
        )
        issues = []

    logger.info(
        "GET /insights/developer/%s: %d개 규칙 반환", developer_id, len(issues)
    )
    return {"developer_id": developer_id, "issues": issues}


@router.get("/team")
async def get_team_insights():
    """
    팀 이번 달 Top 5 이슈 집계 조회.

    date_trunc('month', now())로 현재 월 필터링.
    이번 달 전체 PR에서 가장 많이 발생한 이슈 5개를 반환.
    팀 회고·코드리뷰 미팅 등 팀 단위 개선 지표로 사용.

    Returns:
        {"top_issues": [{"rule_id": ..., "severity": ..., "count": ...}, ...]}
    """
    try:
        from dev2.db import AsyncSessionLocal  # noqa: PLC0415
        async with AsyncSessionLocal() as s:
            r = await s.execute(text("""
                SELECT si.rule_id, si.severity, COUNT(*) as count
                FROM scan_issues si
                JOIN scan_executions se ON si.scan_id = se.id
                WHERE se.scanned_at >= date_trunc('month', now())
                GROUP BY si.rule_id, si.severity
                ORDER BY count DESC
                LIMIT 5
            """))
            top_issues = [dict(row) for row in r.mappings().all()]
    except Exception as exc:
        logger.warning("get_team_insights: DB 조회 실패 — %s | 빈 결과 반환", exc)
        top_issues = []

    return {"top_issues": top_issues}


@router.get("/trends")
async def get_trends():
    """
    개발자별 주간 Critical 이슈 추이 조회.

    date_trunc('week', ...)으로 주 단위 집계.
    Critical 이슈가 줄어드는지 추이를 보여 성장 지표로 활용.
    Dev5 커리큘럼 효과 측정에 사용.

    Returns:
        {"trends": [{"week": ..., "developer_id": ..., "critical_count": ...}, ...]}
    """
    try:
        from dev2.db import AsyncSessionLocal  # noqa: PLC0415
        async with AsyncSessionLocal() as s:
            r = await s.execute(text("""
                SELECT
                    date_trunc('week', se.scanned_at) as week,
                    se.developer_id,
                    SUM(ss.critical) as critical_count
                FROM scan_summaries ss
                JOIN scan_executions se ON ss.scan_id = se.id
                GROUP BY week, se.developer_id
                ORDER BY week
            """))
            trends = [dict(row) for row in r.mappings().all()]
    except Exception as exc:
        logger.warning("get_trends: DB 조회 실패 — %s | 빈 결과 반환", exc)
        trends = []

    return {"trends": trends}
