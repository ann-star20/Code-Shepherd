"""트리거 라우터 — PR 웹훅, 문서 업로드 신호 수신."""

from __future__ import annotations

import hashlib
import hmac
import uuid

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel

from shared.config import get_settings
from shared.contracts import (
    AnalysisContext,
    DeveloperProfile,
    DocumentTriggerPayload,
    M0IngestRequest,
    M2AnalyzeRequest,
    M3VerifyRequest,
    M4EvaluateRequest,
    PRTriggerPayload,
)
from shared.logging import get_logger

from ..clients.api_core_client import call_api_core_pr_ingest
from ..clients.module_clients import (
    call_m0_ingest,
    call_m2_analyze_security,
    call_m2_analyze_static,
    call_m3_analyze_performance,
    call_m3_verify_tests,
    call_m4_evaluate,
)

router = APIRouter()
logger = get_logger(__name__)


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
    analysis_req = M2AnalyzeRequest(
        task_id=task_id,
        pr_id=trigger.pr_id or "",
        pr_diff=trigger.pr_diff,
        context=AnalysisContext(),
        trace_id=trigger.trace_id,
    )
    verify_req = M3VerifyRequest(
        task_id=task_id,
        pr_id=trigger.pr_id or "",
        pr_diff=trigger.pr_diff,
        context=AnalysisContext(),
        trace_id=trigger.trace_id,
    )

    # 결정적 라우팅: PR → m2(static) + m2(security) + m3(tests) + m3(perf) → m4
    try:
        static_result = await call_m2_analyze_static(analysis_req)
        security_result = await call_m2_analyze_security(analysis_req)
        test_result = await call_m3_verify_tests(verify_req)
        perf_result = await call_m3_analyze_performance(verify_req)

        eval_req = M4EvaluateRequest(
            task_id=task_id,
            pr_id=trigger.pr_id or "",
            static_analysis=static_result,
            security_scan=security_result,
            test_verification=test_result,
            performance=perf_result,
            trace_id=trigger.trace_id,
        )
        eval_result = await call_m4_evaluate(eval_req)

        logger.info(
            "pr_trigger_dispatched",
            task_id=task_id,
            trace_id=trigger.trace_id,
            verdict=eval_result.verdict,
        )
        return {
            "task_id": task_id,
            "trace_id": trigger.trace_id,
            "status": "dispatched",
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
