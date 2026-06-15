"""M2 정적 분석·보안 스캔 스텁.

엔드포인트는 MODULE_CONTRACT §Module 2 계약(AgentResult)을 반환한다.
AgentResult는 M2AnalyzeResponse 상위집합이라 m1/m3 호출 경로와 하위호환된다.
(backend/m2/MODULE_CONTRACT.md 참조)
"""

import asyncio
import os
import pathlib
import re
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI

from fastapi.responses import JSONResponse

from app import progress
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

# eval 케이스 데이터셋 루트 (컨테이너 마운트 경로). 케이스별 vulnerable.py를 읽어 분석한다.
M2_CASE_ROOT = os.getenv(
    "M2_CASE_ROOT",
    "/app/service/pj3_data/datasets/JH_PJ3/m2dataset/m2_mixed_case",
)
# case_name 화이트리스트 — 디렉터리 traversal 차단 (영문/숫자/_/- 만 허용)
_CASE_NAME_RE = re.compile(r"^[\w-]+$")


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


def _to_unified_diff(abs_path: str, content: str) -> str:
    """파일 전체를 신규 추가 unified diff로 변환 (run_case.py:_to_unified_diff 이식)."""
    lines = content.splitlines()
    header = f"--- /dev/null\n+++ b/{abs_path}\n@@ -0,0 +1,{len(lines)} @@\n"
    body = "\n".join(f"+{line}" for line in lines)
    return header + body


@app.post("/orchestrate/run-case/{case_name}")
async def run_case(case_name: str) -> JSONResponse:
    """eval 케이스를 실제로 분석 실행하고 task_id를 즉시 반환한다(백그라운드 실행).

    프론트는 반환된 task_id로 GET /orchestrate/status/{task_id}를 폴링해
    파이프라인 단계를 실시간 시각화한다.
    """
    if not _CASE_NAME_RE.match(case_name):
        return JSONResponse({"error": "invalid case_name"}, status_code=400)

    py_file = pathlib.Path(M2_CASE_ROOT) / case_name / "vulnerable.py"
    if not py_file.is_file():
        return JSONResponse({"error": f"case not found: {case_name}"}, status_code=404)

    code = py_file.read_text(encoding="utf-8")
    # 상대경로를 헤더에 쓴다 — analyzer._materialize가 임시 디렉터리에 복원해 분석하므로
    # 실제 데이터셋 파일을 건드리지 않는다(절대경로면 임시루트를 무시하고 원본을 덮어써
    # uvicorn --reload가 분석 중 리로드되어 백그라운드 분석이 죽음).
    rel_path = f"{case_name}/vulnerable.py"
    diff = _to_unified_diff(rel_path, code)

    # case_name 끝 숫자 → pr_number(100+N). 프론트 MIXED_CASES github_pr_number(101~)와 일치.
    m = re.search(r"(\d+)$", case_name)
    pr_number = 100 + int(m.group(1)) if m else None
    pr_id = str(pr_number) if pr_number is not None else case_name

    task_id = str(uuid.uuid4())
    req = M2OrchestrateRequest(
        task_id=task_id,
        pr_id=pr_id,
        pr_diff=diff,
        pr_number=pr_number,
        developer={"id": "00000000-0000-0000-0000-000000000001", "skill_level": "junior", "tech_stack": ["python"]},
    )

    progress.start(task_id)
    asyncio.create_task(run_m2_orchestration(req, task_id))
    return JSONResponse({"task_id": task_id, "pr_id": pr_id})


@app.get("/orchestrate/status/{task_id}")
async def orchestrate_status(task_id: str) -> JSONResponse:
    """run-case로 시작한 분석의 진행상태(단계별 status/ms·결과)를 반환한다."""
    st = progress.get(task_id)
    if st is None:
        return JSONResponse({"error": "task not found"}, status_code=404)
    return JSONResponse(st)


def _display_file(path: str | None) -> str | None:
    """UI 표시용 파일 경로 — run-case의 절대경로는 케이스 기준 상대경로로 축약."""
    if not path:
        return None
    marker = "m2_mixed_case/"
    idx = path.find(marker)
    return path[idx + len(marker):] if idx >= 0 else path


async def _build_review_response(rows: list) -> dict:
    issues = [
        {
            "severity": r["severity"],
            "file": _display_file(r["file"]),
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
