"""M2 정적 분석·보안 스캔 스텁."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.analyzer import analyze
from shared.contracts import M2AnalyzeRequest, M2AnalyzeResponse
from shared.logging import TraceIDMiddleware, configure_logging


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    yield


app = FastAPI(title="code-shepherd m2-analysis-stub", version="0.1.0", lifespan=lifespan)
app.add_middleware(TraceIDMiddleware)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "m2-analysis"}


@app.post("/analyze/static", response_model=M2AnalyzeResponse)
async def analyze_static(payload: M2AnalyzeRequest) -> M2AnalyzeResponse:
    """Pylint / Radon / ESLint 정적 분석."""
    issues, summary, execution_ms = await asyncio.to_thread(
        analyze, payload.pr_diff, "static_analysis"
    )
    return M2AnalyzeResponse(
        task_id=payload.task_id,
        agent="static_analysis",
        issues=issues,
        summary=summary,
        execution_ms=execution_ms,
    )


@app.post("/analyze/security", response_model=M2AnalyzeResponse)
async def analyze_security(payload: M2AnalyzeRequest) -> M2AnalyzeResponse:
    """Bandit / Semgrep 보안 스캔 (OWASP Top 10)."""
    issues, summary, execution_ms = await asyncio.to_thread(
        analyze, payload.pr_diff, "security_scan"
    )
    return M2AnalyzeResponse(
        task_id=payload.task_id,
        agent="security_scan",
        issues=issues,
        summary=summary,
        execution_ms=execution_ms,
    )
