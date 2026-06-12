"""m3 drop-in HTTP 어댑터 — FastAPI, 포트 8004.

엔드포인트:
  POST /review  — m1(Orchestrator) 호출. diff fetch → pipeline → comment 게시 → M3ReviewResponse.
  GET  /review/{owner}/{repo}/{pr_number}  — 프론트 조회. 저장된 결과 반환.

m3 계약 정본: docs/FRONTEND_INTEGRATION.md
실행: uvicorn src.adapters.http_adapter:app --port 8004
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Literal

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from contracts import Finding, ReviewInput, ReviewOutput
from src.graph import run_review_traced

log = logging.getLogger(__name__)

app = FastAPI(title="dev3-http-adapter", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ── 인메모리 결과 저장소 — GET /review가 읽는다 ──────────────────────────────
_result_store: dict[str, dict[str, Any]] = {}

# ── verdict 매핑 ──────────────────────────────────────────────────────────────
_KEYWORD_MAP: dict[str, str] = {
    "CONV-API-001": "동기 HTTP 호출",
    "CONV-TIME-002": "타임존 불일치",
    "CONV-LOG-003": "비구조적 로깅",
    "CONV-DB-004": "N+1 쿼리",
    "CONV-DEP-005": "금지 의존성",
    "CONV-ERR-006": "예외 무음 처리",
    "CONV-CFG-007": "환경변수 직접 접근",
    "CONV-SQL-008": "SQL 인젝션 위험",
}


# ── Pydantic 계약 모델 (shared/contracts 미참조 — 독립 스키마) ────────────────

class M3ReviewRequest(BaseModel):
    task_id: str
    pr_id: str
    repository: str
    pr_number: int
    static_analysis: Any = None
    security_scan: Any = None
    test_verification: Any = None
    performance: Any = None
    developer: Any = None
    trace_id: str | None = None


class M3ReviewResponse(BaseModel):
    task_id: str
    pr_id: str
    verdict: Literal["lgtm", "rework", "escalate"]
    comment_posted: bool
    comment_url: str | None
    persisted: bool
    # 옵셔널 추가 필드 — 팀 정본엔 없음. m1 pydantic 은 unknown 필드를 무시하므로 G1 안전.
    trace: list[dict] | None = None


# ── 내부 헬퍼 ────────────────────────────────────────────────────────────────

def _map_verdict(output: ReviewOutput) -> Literal["lgtm", "rework", "escalate"]:
    if output.gap_report is not None:
        return "escalate"
    violations = [f for f in (output.findings or []) if f.verdict == "violation"]
    return "rework" if violations else "lgtm"


def _verdict_reason(verdict: str, findings: list[Finding]) -> str:
    violations = [f for f in findings if f.verdict == "violation"]
    majors = sum(1 for f in violations if f.severity == "Major")
    if verdict == "rework":
        return f"Major {majors}건 → 수정 요청"
    if verdict == "escalate":
        return "지침공백 — KMS 신규 규칙 제안 첨부"
    return f"위반 0건 → 통과"


def _findings_to_issues(findings: list[Finding], chunks_source_map: dict[str, str] | None = None) -> list[dict]:
    source_map = chunks_source_map or {}
    issues = []
    for f in findings:
        if f.verdict != "violation":
            continue
        issues.append({
            "severity": f.severity,
            "file": f.file or "",
            "line": None,
            "message": f.reasoning or "",
            "rule_id": f.rule_id,
            "suggestion": f.rule_quote or "",
            "rag_context": f.rule_quote or "",
            "source_url": source_map.get(f.rule_id, ""),
        })
    return issues


def _findings_to_rich(findings: list[Finding]) -> list[dict]:
    rich = []
    for f in findings:
        if f.verdict != "violation":
            continue
        rich.append({
            "agent": "dev3",
            "severity": f.severity,
            "keyword": _KEYWORD_MAP.get(f.rule_id, f.rule_id),
            "sub_category": f.rule_id,
            "code_context": "\n".join(f.evidence_lines) if f.evidence_lines else "",
            "code_snippet": "",
            "suggestion": f.reasoning or "",
            "name_of_function": None,
            "programming_language": "python",
            "framework": None,
        })
    return rich


def _store_result(owner: str, repo: str, pr_number: int, output: ReviewOutput,
                  trace: list[dict] | None = None) -> None:
    verdict = _map_verdict(output)
    key = f"{owner}/{repo}/{pr_number}"
    _result_store[key] = {
        "verdict": verdict,
        "verdict_reason": _verdict_reason(verdict, output.findings or []),
        "comment": output.comment_md or "",
        "issues": _findings_to_issues(output.findings or []),
        "rich_issues": _findings_to_rich(output.findings or []),
        "trace": trace or [],
    }


async def _fetch_pr_diff(owner: str, repo: str, pr_number: int) -> str:
    token = os.getenv("GITHUB_TOKEN", "")
    headers: dict[str, str] = {
        "Accept": "application/vnd.github.v3.diff",
        "User-Agent": "dev3-code-review-agent",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}",
            headers=headers,
        )
        r.raise_for_status()
        return r.text


async def _post_github_comment(owner: str, repo: str, pr_number: int, body: str) -> tuple[bool, str | None]:
    token = os.getenv("GITHUB_TOKEN", "")
    if not token or not body:
        return False, None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "dev3-code-review-agent",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments",
            json={"body": body},
            headers=headers,
        )
    if r.status_code == 201:
        return True, r.json().get("html_url")
    log.warning("http_adapter: comment post failed status=%s", r.status_code)
    return False, None


# ── 엔드포인트 ────────────────────────────────────────────────────────────────

@app.post("/review", response_model=M3ReviewResponse)
async def post_review(payload: M3ReviewRequest) -> M3ReviewResponse:
    owner, _, repo = payload.repository.partition("/")

    try:
        diff = await _fetch_pr_diff(owner, repo, payload.pr_number)
    except Exception as exc:
        log.warning("http_adapter: diff fetch failed: %s", exc)
        diff = ""

    inp = ReviewInput(
        diff=diff,
        file_paths=[],
        repo_meta={"pr_number": payload.pr_number, "repository": payload.repository},
    )
    output, trace = await asyncio.to_thread(run_review_traced, inp)

    posted, comment_url = await _post_github_comment(owner, repo, payload.pr_number, output.comment_md)
    _store_result(owner, repo, payload.pr_number, output, trace)

    log.info(
        "http_adapter: review done task_id=%s verdict=%s posted=%s",
        payload.task_id, _map_verdict(output), posted,
    )
    return M3ReviewResponse(
        task_id=payload.task_id,
        pr_id=payload.pr_id,
        verdict=_map_verdict(output),
        comment_posted=posted,
        comment_url=comment_url,
        persisted=True,
        trace=trace,
    )


@app.get("/review/{owner}/{repo}/{pr_number}")
async def get_review(owner: str, repo: str, pr_number: int) -> dict[str, Any]:
    key = f"{owner}/{repo}/{pr_number}"
    stored = _result_store.get(key)
    base = {"owner": owner, "repo": repo, "pr_number": pr_number}
    if not stored:
        return {**base, "found": False, "verdict": None, "verdict_reason": "",
                "comment": "", "issues": [], "rich_issues": []}
    return {**base, "found": True, **stored}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "adapter": "dev3"}
