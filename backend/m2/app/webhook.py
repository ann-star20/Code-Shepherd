"""GitHub PR 웹훅 진입점 — m2 독립 트리거.

설계 전환("모듈별 end-to-end")으로 m1을 거치지 않고 m2가 PR 웹훅을 직접 받는다.
흐름: 서명검증 → action 필터 → payload 파싱 → diff fetch → run_m2_orchestration.

처리 모델: **동기**(Phase 1 분석이 가볍다 — 정적/보안 도구 위주). 결과를 바로 반환한다.
무거워지면 202 accepted + 백그라운드로 전환할 수 있다(추후).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets

from fastapi import APIRouter, Header, HTTPException, Request

from app.clients.github_client import fetch_diff
from app.contract import M2OrchestrateRequest, M2OrchestrateResponse
from app.orchestrator import run_m2_orchestration
from shared.contracts import DeveloperProfile

router = APIRouter()

# 처리할 PR action — 그 외(closed/labeled 등)는 무시한다.
_HANDLED_ACTIONS = {"opened", "reopened", "synchronize", "ready_for_review"}


def verify_signature(secret: str | None, body: bytes, signature: str | None) -> bool:
    """GitHub HMAC-SHA256 서명 검증.

    - secret 미설정(개발 모드): 검증 생략(True).
    - secret 설정: 서명 헤더가 일치해야 True.
    """
    if not secret:
        return True
    if not signature or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _build_request(payload: dict) -> M2OrchestrateRequest | None:
    """GitHub pull_request 웹훅 payload → M2OrchestrateRequest.

    diff_url은 본문에 없으므로 여기서 채우지 않고 호출부에서 fetch 후 주입한다.
    필수 필드(pull_request)가 없으면 None.
    """
    pr = payload.get("pull_request")
    if not isinstance(pr, dict):
        return None
    repo = payload.get("repository") or {}
    author = pr.get("user") or {}
    number = pr.get("number")
    return M2OrchestrateRequest(
        task_id=secrets.token_hex(16),
        pr_id=str(pr.get("id") or number or "unknown"),
        pr_diff="",  # 호출부에서 fetch_diff 결과로 채움
        repository=repo.get("full_name"),
        pr_number=number,
        developer=(
            DeveloperProfile(id=author["login"]) if author.get("login") else None
        ),
        trace_id=f"pr_{secrets.token_hex(6)}",
    )


@router.post("/webhook/github", response_model=M2OrchestrateResponse)
async def github_webhook(
    request: Request,
    x_github_event: str | None = Header(default=None),
    x_hub_signature_256: str | None = Header(default=None),
) -> M2OrchestrateResponse:
    """GitHub PR 웹훅 수신 → 정적+보안 분석 오케스트레이션."""
    body = await request.body()

    secret = os.getenv("GITHUB_WEBHOOK_SECRET")
    if not verify_signature(secret, body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="invalid webhook signature")

    if x_github_event != "pull_request":
        # ping 등 다른 이벤트는 수신만 하고 무시.
        return M2OrchestrateResponse(
            task_id="-",
            pr_id="-",
            status="skip",
            skip_reason=f"unhandled event: {x_github_event}",
        )

    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="invalid JSON body") from None

    action = payload.get("action")
    if action not in _HANDLED_ACTIONS:
        return M2OrchestrateResponse(
            task_id="-",
            pr_id="-",
            status="skip",
            skip_reason=f"unhandled action: {action}",
        )

    req = _build_request(payload)
    if req is None:
        raise HTTPException(status_code=400, detail="missing pull_request in payload")

    pr = payload["pull_request"]
    diff = await fetch_diff(pr.get("diff_url", ""))
    if diff is None:
        # diff를 못 가져오면 분석할 게 없다 → skip(파이프라인 비중단).
        return M2OrchestrateResponse(
            task_id=req.task_id,
            pr_id=req.pr_id,
            status="skip",
            skip_reason="diff fetch 실패",
            trace_id=req.trace_id,
        )

    req.pr_diff = diff
    return await run_m2_orchestration(req)
