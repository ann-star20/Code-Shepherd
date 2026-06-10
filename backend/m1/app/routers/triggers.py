"""트리거 라우터 — PR 웹훅, 문서 업로드 신호 수신."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid

import httpx
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, status

from shared.config import get_settings
from shared.contracts import (
    AnalysisContext,
    DeveloperProfile,
    DocumentTriggerPayload,
    M0IngestRequest,
    M2AnalyzeRequest,
    M3ReviewRequest,
    M3VerifyRequest,
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

# 분석·코멘트를 발사할 PR 액션 화이트리스트. 나머지(closed/edited/labeled/assigned 등)는 무시한다.
# 없으면 Close→Reopen 한 번에 closed+reopened 두 신호가 모두 분석을 돌려 코멘트가 중복된다.
# webhook-gateway/server.py 와 동일한 집합(opened/synchronize/reopened).
_ANALYZABLE_PR_ACTIONS = frozenset({"opened", "reopened", "synchronize"})


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


@router.post("/triggers/pr", status_code=status.HTTP_202_ACCEPTED)
async def receive_pr_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: str | None = Header(default=None),
):
    """GitHub PR 웹훅 수신 — HMAC 서명 검증 직후 즉시 202 접수, 무거운 분석은 백그라운드로.

    GitHub 은 10초 안에 응답을 기대하지만 m3 분석(clone+분석)은 13~41초 걸린다.
    동기로 기다리면 GitHub "timed out" + 웹훅 재전송 → 중복 분석. 따라서 서명만 확인하고
    즉시 202 를 돌려준 뒤, ingest→diff→m2/m3→m3 /review 체인은 BackgroundTasks 로 수행한다.
    (결과는 m3 GET /review 폴링으로 확인 — 별도 콜백 없음.)
    """
    settings = get_settings()
    body = await request.body()

    # 서명 검증은 응답(202) 전에 그대로 — 잘못된/없는 서명은 401, 백그라운드 스케줄 안 함.
    if not _verify_github_hmac(body, x_hub_signature_256, settings.github_webhook_secret):
        logger.warning("webhook_signature_invalid", signature=x_hub_signature_256)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing HMAC signature",
        )

    trace_id = str(uuid.uuid4())
    logger.info("pr_webhook_accepted", trace_id=trace_id)
    background_tasks.add_task(_process_pr_webhook, body, trace_id)
    return {"status": "accepted", "trace_id": trace_id}


async def _process_pr_webhook(body: bytes, trace_id: str) -> None:
    """무거운 분석 체인을 백그라운드에서 수행한다.

    응답(202)은 이미 나갔으므로 절대 raise 하지 않는다 — 받을 곳이 없다.
    skip(미등록 레포 ingest 404, 필드 누락 등)·모듈 실패는 정직하게 로그로만 남긴다.
    최종 동작(코멘트 게시·DB 저장)은 기존과 동일 — m3 /review 가 수행한다.

    NOTE(운영): 단일 워커 BackgroundTasks 는 같은 워커의 이벤트 루프에서 돈다. 다(多)PR 동시
    처리량/내구성(워커 재시작 시 유실)은 보장하지 못한다 — 운영에선 외부 큐(Celery/arq 등)로
    전환해야 한다. 이번 범위 밖(여기선 GitHub 10초 타임아웃 해소가 목표).
    """
    try:
        try:
            raw = json.loads(body)
        except Exception:
            logger.warning("pr_webhook_parse_failed", trace_id=trace_id)
            return

        pr_number = raw.get("number") or raw.get("pull_request", {}).get("number")
        pull_request = raw.get("pull_request") or {}
        action = raw.get("action", "opened")
        author_login = (
            pull_request.get("user", {}).get("login")
            or raw.get("sender", {}).get("login")
        )
        repository = raw.get("repository", {}).get("full_name")
        pr_id = str(pr_number or "")

        logger.info(
            "pr_trigger_received",
            action=action,
            pr_id=pr_id,
            trace_id=trace_id,
            repository=repository,
        )

        # 분석 대상 액션만 처리 — closed/edited/labeled 등은 정직하게 스킵(코멘트 중복 방지).
        if action not in _ANALYZABLE_PR_ACTIONS:
            logger.info(
                "pr_trigger_skipped",
                reason=f"action={action} 분석 대상 아님(중복 코멘트 방지)",
                action=action,
                trace_id=trace_id,
            )
            return

        if not repository or not author_login or not pr_number:
            logger.info(
                "pr_trigger_skipped",
                reason="missing repository, author, or PR number",
                trace_id=trace_id,
            )
            return

        # ── api-core ingest (미등록 레포면 404 → 정직하게 스킵) ──
        try:
            await call_api_core_pr_ingest(
                {
                    "repository_full_name": repository,
                    "sender_github_login": author_login,
                    "pr_number": int(pr_number),
                    "pr_url": pull_request.get("html_url"),
                    "action": action,
                    "pull_request": pull_request,
                }
            )
        except HTTPException as exc:
            if exc.status_code == 404:
                logger.info("pr_trigger_skipped", reason=str(exc.detail), trace_id=trace_id)
            else:
                logger.error(
                    "pr_trigger_ingest_error",
                    status=exc.status_code,
                    error=str(exc.detail),
                    trace_id=trace_id,
                )
            return

        task_id = str(uuid.uuid4())

        # diff_url → 본문 텍스트로 1회 fetch (URL 그대로 m2/m3 로 보내지 않는다).
        diff_text = await _fetch_pr_diff(pull_request.get("diff_url", ""))

        # m3 실 분석(clone→run)용 repo 좌표.
        head = pull_request.get("head") or {}
        clone_url = (head.get("repo") or {}).get("clone_url") or raw.get(
            "repository", {}
        ).get("clone_url")
        commit_sha = head.get("sha")

        analysis_req = M2AnalyzeRequest(
            task_id=task_id,
            pr_id=pr_id,
            pr_diff=diff_text,
            context=AnalysisContext(),
            trace_id=trace_id,
        )
        verify_req = M3VerifyRequest(
            task_id=task_id,
            pr_id=pr_id,
            pr_diff=diff_text,
            clone_url=clone_url,
            commit_sha=commit_sha,
            context=AnalysisContext(),
            trace_id=trace_id,
            developer=DeveloperProfile(id=author_login) if author_login else None,
        )

        # 결정적 라우팅: m2(static)+m2(security)+m3(tests)+m3(perf) → m3(review).
        # 코멘트·판정은 m3 소유(m4 미호출). m3 /review 가 집계→판정→게시→저장까지 수행.
        static_result = await call_m2_analyze_static(analysis_req)
        security_result = await call_m2_analyze_security(analysis_req)
        test_result = await call_m3_verify_tests(verify_req)
        perf_result = await call_m3_analyze_performance(verify_req)

        review_req = M3ReviewRequest(
            task_id=task_id,
            pr_id=pr_id,
            repository=repository,
            pr_number=int(pr_number),
            static_analysis=static_result,
            security_scan=security_result,
            test_verification=test_result,
            performance=perf_result,
            trace_id=trace_id,
        )
        review_result = await call_m3_review(review_req)

        logger.info(
            "pr_trigger_dispatched",
            task_id=task_id,
            trace_id=trace_id,
            verdict=review_result.verdict,
            comment_posted=review_result.comment_posted,
        )
    except Exception as exc:  # noqa: BLE001 — 백그라운드: 절대 raise 금지, 로그만(정직)
        logger.error("pr_trigger_background_error", trace_id=trace_id, error=str(exc))


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
