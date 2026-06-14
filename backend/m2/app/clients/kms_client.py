"""m0 KMS `/kms/search` 호출 client — graceful fallback.

실제 m0 계약(backend/m0/app/routes/kms_routes.py):
  GET /kms/search?q=<쿼리>&limit=<n>&category=<opt>
  → SearchResponse { query, results: [{chunk_id, content, score, ...}], total }

`M0_URL`이 없거나 호출이 실패하면 None을 반환한다(KMS 검색 실패가
m2 분석을 중단시키지 않음 — 빈 context로 진행).
요청/응답 계약(app.contract.KmsSearch*)은 m2 내부에 두고, m0 응답의
부분집합(chunk_id/content/score)만 사용한다 — m0 무수정.
"""

from __future__ import annotations

import os

import httpx

from app.contract import KmsSearchRequest, KmsSearchResponse

_TIMEOUT = 10.0  # 초


def _base_url() -> str | None:
    url = os.getenv("M0_URL") or os.getenv("M0_BASE_URL")
    return url.rstrip("/") if url else None


async def search(req: KmsSearchRequest) -> KmsSearchResponse | None:
    """m0 `GET /kms/search` 호출. 미설정·실패·404 시 None(graceful).

    KmsSearchRequest.query/top_k → m0 쿼리 파라미터 q/limit 로 매핑.
    응답의 results만 취해 KmsSearchResponse로 파싱(추가 필드는 무시).
    """
    base = _base_url()
    if not base:
        return None
    params = {"q": req.query, "limit": req.top_k}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{base}/kms/search", params=params)
            resp.raise_for_status()
            return KmsSearchResponse(**resp.json())
    except (httpx.HTTPError, ValueError):
        return None
