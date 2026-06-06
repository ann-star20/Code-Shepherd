"""트리거 라우터 — PR 웹훅, 문서 업로드 신호 수신."""

from __future__ import annotations

import hashlib
import hmac
import uuid

import httpx
from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel

from shared.config import get_settings
from shared.contracts import (
    AnalysisContext,
    DocumentTriggerPayload,
    M0IngestRequest,
    M2AnalyzeRequest,
    M3ReviewRequest,
    M3VerifyRequest,
    PRTriggerPayload,
)
from shared.logging import get_logger

from ..clients.api_core_client import call_api_core_pr_ingest
from ..clients.module_clients import (
    call_m0_ingest,
    call_m2_analyze_security,
    call_m2_analyze_static,
    call_m3_analyze_performance,
    call_m3_review,
    call_m3_verify_tests,
)

router = APIRouter()
logger = get_logger(__name__)


# diff_url(.diff) 본문 fetch 타임아웃. 데모 레포는 public 이라 토큰 불필요.
_DIFF_FETCH_TIMEOUT_S = 15.0


async def _fetch_pr_diff(diff_url: str) -> str:
    """PR 의 diff_url(.diff)을 본문 텍스트로 1회 fetch.

    m2·m3 는 URL 이 아니라 'diff --git ...' 본문을 기대한다. 따라서 여기서 본문으로
    치환해 보낸다. diff_url 이 비었거나, fetch 실패/비-diff 응답이면 빈 문자열을 돌려준다
    (가짜 diff 를 만들지 않는다 — 빈 본문이면 분석은 빈 결과로 정직하게 흐른다).
    """
    if not diff_url:
        return ""
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=_DIFF_FETCH_TIMEOUT_S) as client:
            resp = await client.get(diff_url)
        if resp.status_code == 200 and resp.text.startswith("diff --git"):
            return resp.text
    except Exception as exc:  # noqa: BLE001 — 네트워크/HTTP 어떤 실패든 정직하게 빈 본문으로
        logger.warning("pr_diff_fetch_failed", url=diff_url, error=str(exc))
        return ""
    return ""


def _verify_github_hmac(body: bytes, signature: str | None, secret: str) -> bool:
    """GitHub HMAC-SHA256 서명 검증."""
    if not signature:
        return False
    if not signature.startswith("sha256="):
        return False
    expected = hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()
    received = signature[len("sha256="):]
    return hmac.compare_digest(expected, received)


@router.post("/triggers/pr")
async def receive_pr_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
):
    """GitHub PR 웹훅 수신 — HMAC 서명 검증 후 m2·m3·m4 호출."""
    settings = get_settings()
    body = await request.body()

    if not _verify_github_hmac(body, x_hub_signature_256, settings.github_webhook_secret):
        logger.warning("webhook_signature_invalid", signature=x_hub_signature_256)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing HMAC signature",
        )

    import json

    try:
        raw = json.loads(body)
    except Exception:
        raw = {}

    pr_number = raw.get("number") or raw.get("pull_request", {}).get("number")
    pull_request = raw.get("pull_request") or {}
    author_login = (
        pull_request.get("user", {}).get("login")
        or raw.get("sender", {}).get("login")
    )
    repository = raw.get("repository", {}).get("full_name")

    trigger = PRTriggerPayload(
        action=raw.get("action", "opened"),
        pr_id=str(pr_number or ""),
        pr_diff=pull_request.get("diff_url", ""),
        sender_login=author_login,
        repository=repository,
        trace_id=str(uuid.uuid4()),
    )

    logger.info(
        "pr_trigger_received",
        action=trigger.action,
        pr_id=trigger.pr_id,
        trace_id=trigger.trace_id,
        repository=repository,
    )

    if not repository or not author_login or not pr_number:
        return {
            "status": "skipped",
            "reason": "missing repository, author, or PR number",
            "trace_id": trigger.trace_id,
        }

    try:
        ingest_result = await call_api_core_pr_ingest(
            {
                "repository_full_name": repository,
                "sender_github_login": author_login,
                "pr_number": int(pr_number),
                "pr_url": pull_request.get("html_url"),
                "action": trigger.action,
                "pull_request": pull_request,
            }
        )
    except HTTPException as exc:
        if exc.status_code == 404:
            return {
                "status": "skipped",
                "reason": exc.detail,
                "trace_id": trigger.trace_id,
            }
        raise

    task_id = str(uuid.uuid4())

    # diff_url → 본문 텍스트로 1회 fetch. URL 그대로 m2/m3 로 보내지 않는다.
    # (ingest 통과 후에 fetch — skip 되는 PR 에 불필요한 네트워크를 쓰지 않게.)
    diff_text = await _fetch_pr_diff(pull_request.get("diff_url", ""))

    # m3 실 분석(clone→run)용 repo 좌표.
    head = pull_request.get("head") or {}
    clone_url = (head.get("repo") or {}).get("clone_url") or raw.get("repository", {}).get(
        "clone_url"
    )
    commit_sha = head.get("sha")

    # m2·m3 둘 다 동일한 diff_text 를 쓴다(빈 문자열이면 분석은 빈 결과로 정직하게).
    analysis_req = M2AnalyzeRequest(
        task_id=task_id,
        pr_id=trigger.pr_id or "",
        pr_diff=diff_text,
        context=AnalysisContext(),
        trace_id=trigger.trace_id,
    )
    verify_req = M3VerifyRequest(
        task_id=task_id,
        pr_id=trigger.pr_id or "",
        pr_diff=diff_text,
        clone_url=clone_url,
        commit_sha=commit_sha,
        context=AnalysisContext(),
        trace_id=trigger.trace_id,
    )

    # 결정적 라우팅: PR → m2(static) + m2(security) + m3(tests) + m3(perf) → m3(review)
    # 코멘트·판정은 m3 소유(m4 미호출). m3 /review 가 집계→판정→코멘트 게시→저장까지 수행.
    try:
        static_result = await call_m2_analyze_static(analysis_req)
        security_result = await call_m2_analyze_security(analysis_req)
        test_result = await call_m3_verify_tests(verify_req)
        perf_result = await call_m3_analyze_performance(verify_req)

        review_req = M3ReviewRequest(
            task_id=task_id,
            pr_id=trigger.pr_id or "",
            repository=repository,
            pr_number=int(pr_number),
            static_analysis=static_result,
            security_scan=security_result,
            test_verification=test_result,
            performance=perf_result,
            trace_id=trigger.trace_id,
        )
        review_result = await call_m3_review(review_req)

        logger.info(
            "pr_trigger_dispatched",
            task_id=task_id,
            trace_id=trigger.trace_id,
            verdict=review_result.verdict,
            comment_posted=review_result.comment_posted,
        )
        return {
            "task_id": task_id,
            "trace_id": trigger.trace_id,
            "status": "dispatched",
            "verdict": review_result.verdict,
            "comment_url": review_result.comment_url,
            "ingest": ingest_result,
        }

    except Exception as exc:
        logger.error("pr_trigger_dispatch_error", task_id=task_id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Module call failed: {exc}",
        ) from exc


@router.post("/triggers/document")
async def receive_document_trigger(
    payload: DocumentTriggerPayload,
):
    """문서 업로드 완료 신호 수신 → m0 호출."""
    trace_id = payload.trace_id or str(uuid.uuid4())
    task_id = str(uuid.uuid4())

    logger.info(
        "document_trigger_received",
        doc_id=payload.doc_id,
        source=payload.source,
        trace_id=trace_id,
    )

    ingest_req = M0IngestRequest(
        task_id=task_id,
        source=payload.source,
        doc_id=payload.doc_id,
        trace_id=trace_id,
    )

    try:
        result = await call_m0_ingest(ingest_req)
        logger.info(
            "document_trigger_dispatched",
            task_id=task_id,
            trace_id=trace_id,
            status=result.status,
        )
        return {"task_id": task_id, "trace_id": trace_id, "status": "dispatched"}

    except Exception as exc:
        logger.error("document_trigger_dispatch_error", task_id=task_id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"m0 call failed: {exc}",
        ) from exc
