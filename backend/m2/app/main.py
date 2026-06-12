"""M2 정적 분석·보안 스캔 스텁.

엔드포인트는 MODULE_CONTRACT §Module 2 계약(AgentResult)을 반환한다.
AgentResult는 M2AnalyzeResponse 상위집합이라 m1/m3 호출 경로와 하위호환된다.
(backend/m2/MODULE_CONTRACT.md 참조)
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.contract import (
    AgentResult,
    M2OrchestrateRequest,
    M2OrchestrateResponse,
)
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
