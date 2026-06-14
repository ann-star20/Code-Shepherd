"""M2 정적 분석·보안 스캔 스텁.

엔드포인트는 MODULE_CONTRACT §Module 2 계약(AgentResult)을 반환한다.
AgentResult는 M2AnalyzeResponse 상위집합이라 m1/m3 호출 경로와 하위호환된다.
(backend/m2/MODULE_CONTRACT.md 참조)
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from fastapi.responses import JSONResponse

from app.contract import (
    AgentResult,
    M2OrchestrateRequest,
    M2OrchestrateResponse,
)
from app.db import fetch_scan_results_by_task
from app.orchestrator import run_m2_orchestration, run_single_agent
from app.webhook import router as webhook_router
from shared.contracts import M2AnalyzeRequest
from shared.logging import TraceIDMiddleware, configure_logging


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    yield


app = FastAPI(title="code-shepherd m2-analysis-stub", version="0.1.0", lifespan=lifespan)
app.add_middleware(TraceIDMiddleware)
app.include_router(webhook_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "m2-analysis"}


@app.post("/analyze/static", response_model=AgentResult)
async def analyze_static(payload: M2AnalyzeRequest) -> AgentResult:
    """Pylint / Radon / ESLint 정적 분석."""
    return await run_single_agent(payload, "static_analysis")


@app.post("/analyze/security", response_model=AgentResult)
async def analyze_security(payload: M2AnalyzeRequest) -> AgentResult:
    """Bandit / Semgrep 보안 스캔 (OWASP Top 10)."""
    return await run_single_agent(payload, "security_scan")


@app.post("/orchestrate/review", response_model=M2OrchestrateResponse)
async def orchestrate_review(payload: M2OrchestrateRequest) -> M2OrchestrateResponse:
    """m2 mini-orchestrator — PR 1건 정적+보안 분석 후 m4 판정까지 조율."""
    return await run_m2_orchestration(payload)


async def _build_review_response(rows: list) -> dict:
    issues = [
        {
            "severity": r["severity"],
            "file": r["file"] or None,
            "line": r["line"],
            "message": r["message"],
            "rule_id": r["rule_id"],
            "suggestion": r["suggestion"],
        }
        for r in rows
    ]
    found = len(issues) > 0
    critical = sum(1 for i in issues if i["severity"] == "Critical")
    verdict = "rework" if critical > 0 else ("lgtm" if found else None)
    return {
        "found": found,
        "verdict": verdict,
        "comment": f"m2 분석 결과: Critical {critical}건 포함 총 {len(issues)}건",
        "issues": issues,
    }


@app.get("/scan-results/{pr_id}")
async def get_scan_results(pr_id: str) -> JSONResponse:
    """pr_id로 저장된 스캔 결과를 SecurityPage 포맷으로 반환."""
    from app.db import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as s:
        rows = (await s.execute(text("""
            SELECT si.severity, si.rule_id, si.file, si.line, si.message, si.suggestion
            FROM scan_executions se
            JOIN scan_issues si ON si.scan_id = se.id
            WHERE se.pr_id = :pr_id
            ORDER BY se.id DESC
        """), {"pr_id": pr_id})).mappings().all()

    return JSONResponse(await _build_review_response(rows))


@app.get("/scan-results/task/{task_id}")
async def get_scan_results_by_task(task_id: str) -> JSONResponse:
    """task_id로 저장된 스캔 결과를 SecurityPage 포맷으로 반환."""
    from app.db import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as s:
        rows = (await s.execute(text("""
            SELECT si.severity, si.rule_id, si.file, si.line, si.message, si.suggestion
            FROM scan_executions se
            JOIN scan_issues si ON si.scan_id = se.id
            WHERE se.task_id = :task_id
            ORDER BY se.id
        """), {"task_id": task_id})).mappings().all()

    return JSONResponse(await _build_review_response(rows))
