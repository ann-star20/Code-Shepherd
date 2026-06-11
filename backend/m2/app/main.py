"""M2 정적 분석·보안 스캔 스텁.

엔드포인트는 MODULE_CONTRACT §Module 2 계약(AgentResult)을 반환한다.
AgentResult는 M2AnalyzeResponse 상위집합이라 m1/m3 호출 경로와 하위호환된다.
(backend/m2/MODULE_CONTRACT.md 참조)
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.analyzer import Agent, analyze
from app.contract import AgentResult, build_agent_result, make_timeout_result
from shared.contracts import M2AnalyzeRequest
from shared.logging import TraceIDMiddleware, configure_logging


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    yield


app = FastAPI(title="code-shepherd m2-analysis-stub", version="0.1.0", lifespan=lifespan)
app.add_middleware(TraceIDMiddleware)


async def _run_agent(payload: M2AnalyzeRequest, agent: Agent) -> AgentResult:
    """분석 실행 → 계약 AgentResult 반환. 실패 시 status=fail 빈 결과(파이프라인 비중단)."""
    try:
        issues, summary, execution_ms = await asyncio.to_thread(analyze, payload.pr_diff, agent)
    except Exception as exc:  # noqa: BLE001 — 어떤 실패든 빈 결과로 graceful degrade
        return make_timeout_result(payload, agent, 0, f"analyze_failed: {exc}")
    return build_agent_result(payload, agent, issues, summary, execution_ms)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "m2-analysis"}


@app.post("/analyze/static", response_model=AgentResult)
async def analyze_static(payload: M2AnalyzeRequest) -> AgentResult:
    """Pylint / Radon / ESLint 정적 분석."""
    return await _run_agent(payload, "static_analysis")


@app.post("/analyze/security", response_model=AgentResult)
async def analyze_security(payload: M2AnalyzeRequest) -> AgentResult:
    """Bandit / Semgrep 보안 스캔 (OWASP Top 10)."""
    return await _run_agent(payload, "security_scan")
