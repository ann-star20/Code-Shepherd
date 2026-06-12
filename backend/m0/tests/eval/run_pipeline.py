"""
KMS 파이프라인 평가 실행 스크립트

golden_dataset.json의 테스트 문서를 /kms/upload API로 전송하고,
처리 완료 후 메타데이터를 수집하여 pipeline_output.json으로 저장한다.

사용법:
    uv run python tests/eval/run_pipeline.py
    uv run python tests/eval/run_pipeline.py --base-url http://localhost:8000
    uv run python tests/eval/run_pipeline.py --doc-id md_01 md_02

Security Guardrail 적용 환경:
    EVAL_AUTH_TOKEN=<jwt_token> uv run python tests/eval/run_pipeline.py
    또는 --token <jwt_token> 플래그 사용
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

EVAL_DIR = Path(__file__).parent
GOLDEN_PATH = EVAL_DIR / "golden_dataset.json"
RESULTS_DIR = EVAL_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)

TERMINAL_STATUSES = {"stored", "hitl_pending", "failed", "stored_partial"}
DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_POLL_INTERVAL = 5      # 초
DEFAULT_MAX_RETRIES = 60       # 최대 5분 (5s * 60)


# ---------------------------------------------------------------------------
# 데이터 로더
# ---------------------------------------------------------------------------

def load_eval_docs(doc_ids: list[str] | None = None) -> list[dict]:
    """golden_dataset.json에서 실제 파일이 존재하는 문서만 반환한다."""
    data = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    docs = []
    for entry in data["documents"]:
        if doc_ids and entry["id"] not in doc_ids:
            continue
        file_path = EVAL_DIR / entry["file"]
        if not file_path.exists():
            logger.warning("파일 없음 — 스킵: %s", file_path)
            continue
        docs.append({
            "id": entry["id"],
            "file": entry["file"],
            "file_type": entry["file_type"],
            "file_path": file_path,
        })
    return docs


# ---------------------------------------------------------------------------
# API 클라이언트 함수
# ---------------------------------------------------------------------------

async def upload_document(base_url: str, file_path: Path, token: str | None = None) -> str:
    """
    POST /kms/upload 로 파일을 업로드하고 doc_id를 반환한다.

    token: Bearer 토큰 (Security Guardrail 환경). None이면 인증 헤더 미포함.
    """
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(timeout=60.0) as client:
        with open(file_path, "rb") as f:
            response = await client.post(
                f"{base_url}/kms/upload",
                files={"file": (file_path.name, f, _mime_type(file_path))},
                data={"source": "upload"},
                headers=headers,
            )
        response.raise_for_status()
        return response.json()["doc_id"]


async def poll_until_done(
    base_url: str,
    doc_id: str,
    poll_interval: float = DEFAULT_POLL_INTERVAL,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> dict:
    """
    GET /kms/status/{doc_id} 를 폴링하여 처리 완료 상태를 반환한다.
    TERMINAL_STATUSES에 도달하거나 max_retries 초과 시 종료.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        for attempt in range(max_retries):
            response = await client.get(f"{base_url}/kms/status/{doc_id}")
            response.raise_for_status()
            data = response.json()
            status = data.get("status", "unknown")

            if status in TERMINAL_STATUSES:
                return data

            if attempt < max_retries - 1:
                await asyncio.sleep(poll_interval)

    raise TimeoutError(
        f"doc_id={doc_id} 처리 완료 대기 시간 초과 "
        f"({max_retries * poll_interval}초)"
    )


async def fetch_metadata(base_url: str, doc_id: str) -> dict:
    """GET /kms/docs/{doc_id}/metadata + /entities + /details 로 메타데이터를 반환한다."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        meta_resp = await client.get(f"{base_url}/kms/docs/{doc_id}/metadata")
        meta_resp.raise_for_status()
        data = meta_resp.json()

        entities: list[dict] = []
        try:
            ent_resp = await client.get(f"{base_url}/kms/docs/{doc_id}/entities")
            if ent_resp.status_code == 200:
                entities = ent_resp.json().get("entities") or []
        except Exception as e:
            logger.warning("entities 조회 실패 doc_id=%s: %s", doc_id, e)

        quality_score: float = 0.0
        try:
            det_resp = await client.get(f"{base_url}/kms/docs/{doc_id}/details")
            if det_resp.status_code == 200:
                quality_score = float(det_resp.json().get("quality_score") or 0.0)
        except Exception as e:
            logger.warning("details 조회 실패 doc_id=%s: %s", doc_id, e)

    # entities를 {type: [name, ...]} 형식으로 변환 (golden_dataset.json / run_eval.py 호환)
    entities_by_type: dict[str, list[str]] = {}
    for e in entities:
        if not e.get("name"):
            continue
        etype = e.get("type") or "other"
        entities_by_type.setdefault(etype, []).append(e["name"])

    return {
        "title": data.get("title"),
        "category": data.get("category"),
        "tags": data.get("tags") or [],
        "entities": entities_by_type,
        "quality_score": quality_score,
    }


# ---------------------------------------------------------------------------
# 출력 형식
# ---------------------------------------------------------------------------

def build_output_entry(
    golden_id: str,
    doc_id: str,
    file_type: str,
    title: str | None,
    category: str | None,
    tags: list[str],
    entities: dict,
    quality_score: float,
    status: str,
    processing_time_ms: float | None = None,
) -> dict:
    """run_eval.py의 load_results_from_file()이 읽을 수 있는 형식으로 반환한다."""
    return {
        "golden_id":           golden_id,
        "doc_id":              doc_id,
        "file_type":           file_type,
        "title":               title,
        "category":            category,
        "tags":                tags,
        "entities":            entities,
        "quality_score":       quality_score,
        "status":              status,
        "processing_time_ms":  processing_time_ms,
    }


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

def _mime_type(file_path: Path) -> str:
    ext = file_path.suffix.lower()
    return {
        ".md":   "text/markdown",
        ".pdf":  "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".txt":  "text/plain",
    }.get(ext, "application/octet-stream")


# ---------------------------------------------------------------------------
# 메인 실행
# ---------------------------------------------------------------------------

async def run(
    base_url: str,
    doc_ids: list[str] | None,
    output_path: Path,
    poll_interval: float,
    max_retries: int,
    token: str | None = None,
) -> None:
    docs = load_eval_docs(doc_ids)
    if not docs:
        logger.error("평가 가능한 문서 없음")
        sys.exit(1)

    if token:
        logger.info("Security Guardrail: Bearer 토큰 인증 활성화")

    logger.info("평가 대상: %d개 문서", len(docs))
    results: list[dict] = []

    for i, doc in enumerate(docs, 1):
        golden_id = doc["id"]
        file_path: Path = doc["file_path"]
        logger.info("[%d/%d] %s (%s)", i, len(docs), golden_id, file_path.name)

        try:
            t_start = time.monotonic()

            # 1. 업로드
            doc_id = await upload_document(base_url, file_path, token=token)
            logger.info("  업로드 완료 → doc_id=%s", doc_id)

            # 2. 처리 완료 대기
            status_data = await poll_until_done(
                base_url, doc_id, poll_interval, max_retries
            )
            status = status_data.get("status", "unknown")
            processing_time_ms = round((time.monotonic() - t_start) * 1000)
            logger.info("  처리 완료 → status=%s (%dms)", status, processing_time_ms)

            # 3. 메타데이터 수집 (quality_score도 /details에서 가져옴)
            meta = await fetch_metadata(base_url, doc_id)
            quality_score = meta.get("quality_score", 0.0)
            logger.info(
                "  메타데이터 → title=%s, category=%s, tags=%d개, quality_score=%.2f",
                meta["title"], meta["category"], len(meta["tags"]), quality_score,
            )

            results.append(build_output_entry(
                golden_id=golden_id,
                doc_id=doc_id,
                file_type=doc["file_type"],
                title=meta["title"],
                category=meta["category"],
                tags=meta["tags"],
                entities=meta["entities"],
                quality_score=quality_score,
                status=status,
                processing_time_ms=processing_time_ms,
            ))

        except TimeoutError as e:
            logger.error("  타임아웃: %s", e)
            results.append(build_output_entry(
                golden_id=golden_id,
                doc_id="",
                file_type=doc["file_type"],
                title=None,
                category=None,
                tags=[],
                entities={},
                quality_score=0.0,
                status="timeout",
            ))
        except Exception as e:
            logger.error("  오류 발생: %s", e)
            results.append(build_output_entry(
                golden_id=golden_id,
                doc_id="",
                file_type=doc["file_type"],
                title=None,
                category=None,
                tags=[],
                entities={},
                quality_score=0.0,
                status="error",
            ))

    output_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("결과 저장 완료: %s (%d건)", output_path, len(results))


def main() -> None:
    import os as _os

    parser = argparse.ArgumentParser(description="KMS 파이프라인 평가 실행")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--doc-id", nargs="*", help="평가할 문서 ID (생략 시 전체)")
    parser.add_argument(
        "--output",
        type=Path,
        default=RESULTS_DIR / "pipeline_output.json",
    )
    parser.add_argument("--poll-interval", type=float, default=DEFAULT_POLL_INTERVAL)
    parser.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES)
    parser.add_argument(
        "--token",
        default=_os.environ.get("EVAL_AUTH_TOKEN"),
        help="Bearer 토큰 (Security Guardrail 환경). EVAL_AUTH_TOKEN 환경변수로도 설정 가능.",
    )
    args = parser.parse_args()

    asyncio.run(run(
        base_url=args.base_url,
        doc_ids=args.doc_id,
        output_path=args.output,
        poll_interval=args.poll_interval,
        max_retries=args.max_retries,
        token=args.token,
    ))


if __name__ == "__main__":
    main()
