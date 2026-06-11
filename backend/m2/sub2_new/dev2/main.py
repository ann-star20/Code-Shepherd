"""
main.py — Dev2 FastAPI 애플리케이션 진입점

Dev2 에이전트 서비스의 FastAPI 앱을 조립하고 라우터를 등록한다.

라우터 구조:
    scan_router     → POST /scan                     (트리거: 비동기 PR 분석 접수)
    insights_router → GET  /insights/developer/{id}  (개발자 통계)
                    → GET  /insights/team             (팀 통계)
                    → GET  /insights/trends           (시계열 추이)
    issues_router   → PATCH /issues/{id}/dismiss      (오탐 표시)
    health          → GET  /health                    (서비스 상태 확인)

설계 원칙:
    - main.py는 "조립만" 담당. 비즈니스 로직은 각 라우터 파일에 위치.
    - 라우터 분리 이유:
        1. 관심사 분리 (scan ≠ insights ≠ issues)
        2. 6인 병렬 개발 시 파일 충돌 방지 (CLAUDE.md §15)
        3. 테스트 독립성: 각 라우터를 별도 mock으로 격리 가능

실행 방법:
    uvicorn dev2.main:app --reload --port 8002

Swagger 문서:
    http://localhost:8002/docs   (자동 생성 — tags 기준 그룹화)
"""

import logging
import os

from dotenv import load_dotenv

# .env 로드 — DATABASE_URL 등 환경변수를 db.py가 읽기 전에 설정
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from fastapi import FastAPI

from dev2.api.aggregate import router as aggregate_router
from dev2.api.insights import router as insights_router
from dev2.api.issues import router as issues_router
from dev2.api.scan import router as scan_router

logger = logging.getLogger(__name__)

# ── FastAPI 앱 ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Dev2: Static Analysis + Security Scan Agent",
    description=(
        "PR diff를 받아 정적 분석(Pylint/ESLint)과 보안 스캔(Bandit/pip-audit)을 수행하고 "
        "LLM(claude-sonnet-4-6)으로 심각도를 판단하는 Dev2 에이전트 서비스.\n\n"
        "- POST /scan: LangGraph 파이프라인 비동기 트리거 (202 Accepted)\n"
        "- GET /insights/*: 분석 결과 통계 조회\n"
        "- PATCH /issues/{id}/dismiss: 오탐 마킹"
    ),
    version="0.1.0",
)

# ── 라우터 등록 ───────────────────────────────────────────────────────────────

app.include_router(scan_router)        # POST /scan
app.include_router(aggregate_router)   # POST /aggregate  (파이프라인 2: 취합→코멘트→알림)
app.include_router(insights_router)    # GET  /insights/*  (prefix="/insights")
app.include_router(issues_router)      # PATCH /issues/*   (prefix="/issues")


# ── 헬스체크 ─────────────────────────────────────────────────────────────────

@app.get("/health", tags=["health"])
async def health():
    """
    서비스 상태 확인 엔드포인트.

    Docker Compose / Kubernetes liveness probe용.
    DB 연결 상태는 포함하지 않음 — 빠른 응답 보장.

    Returns:
        {"status": "ok", "service": "dev2"}
    """
    return {"status": "ok", "service": "dev2"}
