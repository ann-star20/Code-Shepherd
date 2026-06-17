"""하위 모듈 httpx async 클라이언트 — 호출만, 결과 가공 없음."""

from __future__ import annotations

import time

import httpx

from shared.config import get_settings
from shared.contracts import (
    M0IngestRequest,
    M0IngestResponse,
    M2AnalyzeRequest,
    M2AnalyzeResponse,
    M3ReviewRequest,
    M3ReviewResponse,
    M3VerifyRequest,
    M3VerifyResponse,
    M4EvaluateRequest,
    M4EvaluateResponse,
)
from shared.logging import get_logger

logger = get_logger(__name__)


async def call_m0_ingest(payload: M0IngestRequest) -> M0IngestResponse:
    """m0 /ingest 호출."""
    settings = get_settings()
    start = time.monotonic()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.m0_url}/ingest",
            json=payload.model_dump(),
            timeout=30.0,
        )
    elapsed_ms = int((time.monotonic() - start) * 1000)
    logger.info(
        "module_call",
        module="m0",
        endpoint="/ingest",
        status=resp.status_code,
        elapsed_ms=elapsed_ms,
        trace_id=payload.trace_id,
        task_id=payload.task_id,
    )
    resp.raise_for_status()
    return M0IngestResponse(**resp.json())


async def call_m2_analyze_static(payload: M2AnalyzeRequest) -> M2AnalyzeResponse:
    """m2 /analyze/static 호출."""
    settings = get_settings()
    start = time.monotonic()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.m2_url}/analyze/static",
            json=payload.model_dump(),
            timeout=60.0,
        )
    elapsed_ms = int((time.monotonic() - start) * 1000)
    logger.info(
        "module_call",
        module="m2",
        endpoint="/analyze/static",
        status=resp.status_code,
        elapsed_ms=elapsed_ms,
        trace_id=payload.trace_id,
        task_id=payload.task_id,
    )
    resp.raise_for_status()
    return M2AnalyzeResponse(**resp.json())


async def call_m2_analyze_security(payload: M2AnalyzeRequest) -> M2AnalyzeResponse:
    """m2 /analyze/security 호출."""
    settings = get_settings()
    start = time.monotonic()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.m2_url}/analyze/security",
            json=payload.model_dump(),
            timeout=60.0,
        )
    elapsed_ms = int((time.monotonic() - start) * 1000)
    logger.info(
        "module_call",
        module="m2",
        endpoint="/analyze/security",
        status=resp.status_code,
        elapsed_ms=elapsed_ms,
        trace_id=payload.trace_id,
        task_id=payload.task_id,
    )
    resp.raise_for_status()
    return M2AnalyzeResponse(**resp.json())


async def call_m3_verify_tests(payload: M3VerifyRequest) -> M3VerifyResponse:
    """m3 /verify/tests 호출."""
    settings = get_settings()
    start = time.monotonic()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.m3_url}/verify/tests",
            json=payload.model_dump(),
            timeout=60.0,
        )
    elapsed_ms = int((time.monotonic() - start) * 1000)
    logger.info(
        "module_call",
        module="m3",
        endpoint="/verify/tests",
        status=resp.status_code,
        elapsed_ms=elapsed_ms,
        trace_id=payload.trace_id,
        task_id=payload.task_id,
    )
    resp.raise_for_status()
    return M3VerifyResponse(**resp.json())


async def call_m3_analyze_performance(payload: M3VerifyRequest) -> M3VerifyResponse:
    """m3 /analyze/performance 호출."""
    settings = get_settings()
    start = time.monotonic()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.m3_url}/analyze/performance",
            json=payload.model_dump(),
            timeout=60.0,
        )
    elapsed_ms = int((time.monotonic() - start) * 1000)
    logger.info(
        "module_call",
        module="m3",
        endpoint="/analyze/performance",
        status=resp.status_code,
        elapsed_ms=elapsed_ms,
        trace_id=payload.trace_id,
        task_id=payload.task_id,
    )
    resp.raise_for_status()
    return M3VerifyResponse(**resp.json())


async def call_m3_review(payload: M3ReviewRequest) -> M3ReviewResponse:
    """m3 /review 호출 — 4결과 집계→판정→코멘트 게시→저장. (코멘트·판정은 m3 소유)"""
    settings = get_settings()
    start = time.monotonic()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.m3_url}/review",
            json=payload.model_dump(),
            timeout=60.0,
        )
    elapsed_ms = int((time.monotonic() - start) * 1000)
    logger.info(
        "module_call",
        module="m3",
        endpoint="/review",
        status=resp.status_code,
        elapsed_ms=elapsed_ms,
        trace_id=payload.trace_id,
        task_id=payload.task_id,
    )
    resp.raise_for_status()
    return M3ReviewResponse(**resp.json())


async def call_m4_evaluate(payload: M4EvaluateRequest) -> M4EvaluateResponse:
    """m4 /evaluate 호출."""
    settings = get_settings()
    start = time.monotonic()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.m4_url}/evaluate",
            json=payload.model_dump(),
            timeout=60.0,
        )
    elapsed_ms = int((time.monotonic() - start) * 1000)
    logger.info(
        "module_call",
        module="m4",
        endpoint="/evaluate",
        status=resp.status_code,
        elapsed_ms=elapsed_ms,
        trace_id=payload.trace_id,
        task_id=payload.task_id,
    )
    resp.raise_for_status()
    return M4EvaluateResponse(**resp.json())
