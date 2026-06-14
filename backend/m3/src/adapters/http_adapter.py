"""m3 drop-in HTTP 어댑터 — FastAPI, 포트 8004.

엔드포인트:
  POST /review  — m1(Orchestrator) 호출. diff fetch → pipeline → comment 게시 → M3ReviewResponse.
  GET  /review/{owner}/{repo}/{pr_number}  — 프론트 조회. 저장된 결과 반환.

m3 계약 정본: docs/FRONTEND_INTEGRATION.md
실행: uvicorn src.adapters.http_adapter:app --port 8004
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
from typing import Any, Literal

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from contracts import Finding, ReviewInput, ReviewOutput
from src.adapters.db_adapter import insert_review_issues
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

# ── SSE 스트림 저장소 — /review/stream/{} SSE 구독자가 읽는다 ────────────────

class _PrStream:
    """webhook 파이프라인 이벤트를 버퍼링해서 SSE 구독자에게 전달한다.

    push()는 asyncio 이벤트 루프 스레드에서만 호출(call_soon_threadsafe 경유).
    subscribe()는 async generator — 새 이벤트 대기 후 순서대로 yield.
    """

    def __init__(self) -> None:
        self._events: list[dict] = []
        self._done: bool = False
        self._signal: asyncio.Event = asyncio.Event()

    def push(self, event: dict) -> None:
        self._events.append(event)
        if event.get("type") in ("done", "error"):
            self._done = True
        self._signal.set()

    async def subscribe(self):
        pos = 0
        while True:
            while pos < len(self._events):
                yield self._events[pos]
                pos += 1
            if self._done:
                break
            self._signal.clear()
            # double-check: clear() 사이에 이벤트가 도착했을 수 있음
            if pos < len(self._events):
                continue
            await self._signal.wait()


_pr_streams: dict[str, _PrStream] = {}


def _pr_key(owner: str, repo: str, pr_number: int) -> str:
    return f"{owner}/{repo}/{pr_number}"


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

# 팀 /verify/tests + /analyze/performance 스텁용 (m1이 /review 전에 호출)
class _TeamVerifyRequest(BaseModel):
    task_id: str
    pr_id: str
    pr_diff: str = ""
    clone_url: str | None = None
    commit_sha: str | None = None
    trace_id: str | None = None
    context: Any = None
    developer: Any = None


class _TeamIssueSummary(BaseModel):
    critical: int = 0
    major: int = 0
    minor: int = 0


class _TeamVerifyResponse(BaseModel):
    task_id: str
    agent: Literal["test_verification", "performance"]
    issues: list[Any] = []
    summary: _TeamIssueSummary = _TeamIssueSummary()
    metrics: dict | None = None
    execution_ms: int = 0


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
    # SSE 스트림 생성 — /review/stream 구독자가 실시간으로 붙을 수 있도록
    key = _pr_key(owner, repo, payload.pr_number)
    stream = _PrStream()
    _pr_streams[key] = stream
    loop = asyncio.get_running_loop()

    def emit(event: dict) -> None:
        loop.call_soon_threadsafe(stream.push, event)

    output, trace = await asyncio.to_thread(run_review_traced, inp, emit)

    posted, comment_url = await _post_github_comment(owner, repo, payload.pr_number, output.comment_md)
    _store_result(owner, repo, payload.pr_number, output, trace)
    insert_review_issues(output.findings or [], payload.pr_number, payload.repository)

    stored = _result_store[key]
    stream.push({
        "type": "done",
        "result": {
            "verdict": stored["verdict"],
            "verdict_reason": stored.get("verdict_reason", ""),
            "comment": stored["comment"],
            "issues": stored["issues"],
            "trace": stored.get("trace", []),
        },
    })

    async def _cleanup() -> None:
        await asyncio.sleep(120)
        _pr_streams.pop(key, None)
    asyncio.create_task(_cleanup())

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


@app.post("/verify/tests", response_model=_TeamVerifyResponse)
async def verify_tests(payload: _TeamVerifyRequest) -> _TeamVerifyResponse:
    """팀 m1 파이프라인 호환 스텁 — 실 테스트 분석 없이 빈 pass 반환."""
    return _TeamVerifyResponse(task_id=payload.task_id, agent="test_verification")


@app.post("/analyze/performance", response_model=_TeamVerifyResponse)
async def analyze_performance(payload: _TeamVerifyRequest) -> _TeamVerifyResponse:
    """팀 m1 파이프라인 호환 스텁 — 실 성능 분석 없이 빈 pass 반환."""
    return _TeamVerifyResponse(task_id=payload.task_id, agent="performance")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "adapter": "dev3"}


# ── GitHub Webhook (FastAPI) ──────────────────────────────────────────────────
# ngrok 터널을 포트 8004로 연결하면 webhook + SSE가 같은 프로세스에서 동작한다.

async def _run_with_stream(
    owner: str, repo: str, pr_number: int, full_name: str, pr_author: str | None,
) -> None:
    """webhook 이벤트를 _PrStream에 push하면서 파이프라인을 실행한다."""
    key = _pr_key(owner, repo, pr_number)
    stream = _PrStream()
    _pr_streams[key] = stream
    loop = asyncio.get_running_loop()

    def emit(event: dict) -> None:
        # asyncio.to_thread 내부(sync 스레드) → 이벤트 루프로 안전하게 전달
        loop.call_soon_threadsafe(stream.push, event)

    try:
        diff = await _fetch_pr_diff(owner, repo, pr_number)
    except Exception as exc:
        stream.push({"type": "error", "message": f"diff fetch: {exc}"})
        return

    inp = ReviewInput(
        diff=diff,
        file_paths=[],
        repo_meta={"pr_number": pr_number, "repository": full_name},
    )
    try:
        output, trace = await asyncio.to_thread(run_review_traced, inp, emit)
    except Exception as exc:
        stream.push({"type": "error", "message": f"pipeline: {exc}"})
        return

    posted, _ = await _post_github_comment(owner, repo, pr_number, output.comment_md)
    _store_result(owner, repo, pr_number, output, trace)
    insert_review_issues(output.findings or [], pr_number, full_name)

    stored = _result_store[key]
    stream.push({
        "type": "done",
        "result": {
            "verdict": stored["verdict"],
            "verdict_reason": stored.get("verdict_reason", ""),
            "comment": stored["comment"],
            "issues": stored["issues"],
            "trace": stored.get("trace", []),
        },
    })
    log.info("webhook: pipeline done pr=%s/%s#%s posted=%s", owner, repo, pr_number, posted)

    async def _cleanup() -> None:
        await asyncio.sleep(120)
        _pr_streams.pop(key, None)
    asyncio.create_task(_cleanup())


@app.post("/webhook")
async def webhook_handler(request: Request) -> dict[str, Any]:
    """GitHub pull_request 웹훅 수신 → 파이프라인 실행 + SSE 스트리밍."""
    raw = await request.body()
    sig = request.headers.get("X-Hub-Signature-256", "")
    secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    if secret:
        expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return {"error": "invalid signature"}

    event_type = request.headers.get("X-GitHub-Event", "")
    data: dict = json.loads(raw) if raw else {}

    if event_type == "pull_request" and data.get("action") in ("opened", "synchronize"):
        full_name: str = data["repository"]["full_name"]
        pr_number: int = data["pull_request"]["number"]
        pr_author: str | None = data["pull_request"].get("user", {}).get("login")
        owner, _, repo = full_name.partition("/")
        asyncio.create_task(_run_with_stream(owner, repo, pr_number, full_name, pr_author))
        log.info("webhook: accepted PR #%s %s action=%s", pr_number, full_name, data.get("action"))
        return {"status": "accepted", "pr": pr_number}

    return {"status": "ignored", "event": event_type}


# ── SSE 스트리밍 엔드포인트 ───────────────────────────────────────────────────

@app.get("/review/stream/{owner}/{repo}/{pr_number}")
async def stream_review_events(owner: str, repo: str, pr_number: int) -> StreamingResponse:
    """웹훅 트리거 파이프라인의 노드 진행 상황을 SSE로 실시간 전달한다.

    이벤트 타입:
      waiting   — 파이프라인 시작 대기 중 (1초 간격)
      node_start — 노드 실행 시작 {node, label}
      node_done  — 노드 완료 {node, label, ms, summary, ok}
      done       — 파이프라인 완료 {result: {verdict, comment, issues, trace}}
      error      — 오류 {message}
    """
    async def generate():
        key = _pr_key(owner, repo, pr_number)

        # 이미 완료된 결과가 캐시에 있고 활성 스트림이 없으면 즉시 반환
        stored = _result_store.get(key)
        if stored and key not in _pr_streams:
            payload = {
                "type": "done",
                "result": {
                    "verdict": stored["verdict"],
                    "verdict_reason": stored.get("verdict_reason", ""),
                    "comment": stored["comment"],
                    "issues": stored["issues"],
                    "trace": stored.get("trace", []),
                },
            }
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            return

        # 활성 스트림이 없으면 최대 60초 대기 (webhook 아직 미도착)
        if key not in _pr_streams:
            for _ in range(60):
                yield f"data: {json.dumps({'type': 'waiting'})}\n\n"
                await asyncio.sleep(1.0)
                if key in _pr_streams:
                    break
            else:
                stored = _result_store.get(key)
                if stored:
                    yield f"data: {json.dumps({'type': 'done', 'result': stored}, ensure_ascii=False)}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'webhook signal not received within 60s'})}\n\n"
                return

        async for event in _pr_streams[key].subscribe():
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
