"""
DB에 저장된 최근 문서들의 메타데이터를 API로 수집해
pipeline_output.json을 재구성한다.

사용법:
    uv run python tests/eval/rebuild_pipeline_output.py --base-url http://localhost:8002
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

EVAL_DIR = Path(__file__).parent
RESULTS_DIR = EVAL_DIR / "results"

GOLDEN_ID_MAP = {
    "md_01_tech_intro.md":           "md_01",
    "md_02_onboarding_guide.md":     "md_02",
    "md_03_api_reference.md":        "md_03",
    "md_04_security_policy.md":      "md_04",
    "md_05_project_retrospective.md":"md_05",
    "md_06_rag_system_design.md":    "md_06",
    "md_07_ml_ops_guide.md":         "md_07",
    "md_08_incident_report.md":      "md_08",
    "md_09_data_governance.md":      "md_09",
    "md_10_code_review_guide.md":    "md_10",
    "pdf_01_text.pdf":               "pdf_01",
    "pdf_02_table.pdf":              "pdf_02",
    "pdf_03_complex.pdf":            "pdf_03",
    "docx_02_policy.docx":           "docx_02",
    "pptx_01_presentation.pptx":     "pptx_01",
}

EXT_MAP = {
    "md": "md", "pdf": "pdf", "docx": "docx", "pptx": "pptx", "txt": "txt",
}


async def fetch_doc_list(base_url: str, token: str | None = None) -> list[dict]:
    """DB의 최근 15개 문서를 /kms/docs API로 조회한다."""
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{base_url}/kms/docs",
            params={"limit": 30, "status": "stored"},
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("documents") or data if isinstance(data, list) else []


async def fetch_metadata(
    base_url: str, doc_id: str, token: str | None = None
) -> dict:
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        meta = (await client.get(
            f"{base_url}/kms/docs/{doc_id}/metadata", headers=headers
        )).json()
        try:
            ents = (await client.get(
                f"{base_url}/kms/docs/{doc_id}/entities", headers=headers
            )).json()
            entities = ents.get("entities") or []
        except Exception:
            entities = []
        try:
            det = (await client.get(
                f"{base_url}/kms/docs/{doc_id}/details", headers=headers
            )).json()
            quality_score = det.get("quality_score", 0.0)
            processing_time_ms = det.get("processing_time_ms")
        except Exception:
            quality_score = 0.0
            processing_time_ms = None

        # entities 변환: list[{type, name}] → {type: [name, ...]}
        ent_dict: dict[str, list[str]] = {}
        if isinstance(entities, list):
            for e in entities:
                t = e.get("entity_type", "Unknown")
                n = e.get("name", "")
                ent_dict.setdefault(t, []).append(n)

        return {
            "title": meta.get("title"),
            "category": meta.get("category"),
            "tags": meta.get("tags") or [],
            "entities": ent_dict,
            "quality_score": quality_score,
            "processing_time_ms": processing_time_ms,
        }


async def run(base_url: str, token: str | None = None) -> None:
    # 현재 pipeline_output.json 읽기
    output_path = RESULTS_DIR / "pipeline_output.json"
    existing: dict[str, dict] = {}
    if output_path.exists():
        for entry in json.loads(output_path.read_text(encoding="utf-8")):
            gid = entry.get("golden_id", "")
            if gid and entry.get("status") != "error":
                existing[gid] = entry

    logger.info("기존 유효 항목: %d개", len(existing))

    # DB에서 최근 문서 목록 조회
    try:
        docs = await fetch_doc_list(base_url, token=token)
    except Exception as e:
        logger.error("문서 목록 조회 실패: %s", e)
        docs = []

    # original_filename 기준으로 golden_id 매핑
    db_docs: dict[str, dict] = {}
    for doc in docs:
        fname = doc.get("original_filename") or doc.get("filename") or ""
        gid = GOLDEN_ID_MAP.get(fname)
        if gid and gid not in db_docs:
            db_docs[gid] = doc

    logger.info("DB에서 찾은 문서: %d개", len(db_docs))

    results = []
    for gid in GOLDEN_ID_MAP.values():
        if gid in existing:
            results.append(existing[gid])
            logger.info("  %s — 기존 결과 사용", gid)
            continue

        doc = db_docs.get(gid)
        if not doc:
            logger.warning("  %s — DB에 없음, error로 기록", gid)
            results.append({
                "golden_id": gid,
                "doc_id": "",
                "file_type": gid.split("_")[0],
                "title": None, "category": None,
                "tags": [], "entities": {},
                "quality_score": 0.0,
                "status": "error",
                "processing_time_ms": None,
            })
            continue

        doc_id = doc.get("doc_id") or doc.get("id") or ""
        status = doc.get("upload_status") or doc.get("status") or "stored"
        file_type = doc.get("file_type") or gid.split("_")[0]

        try:
            meta = await fetch_metadata(base_url, doc_id, token=token)
            logger.info("  %s — 메타데이터 수집 완료 (%s)", gid, status)
        except Exception as e:
            logger.error("  %s — 메타데이터 수집 실패: %s", gid, e)
            meta = {"title": None, "category": None, "tags": [], "entities": {},
                    "quality_score": 0.0, "processing_time_ms": None}

        results.append({
            "golden_id": gid,
            "doc_id": doc_id,
            "file_type": file_type,
            "title": meta["title"],
            "category": meta["category"],
            "tags": meta["tags"],
            "entities": meta["entities"],
            "quality_score": meta["quality_score"],
            "status": status,
            "processing_time_ms": meta["processing_time_ms"],
        })

    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("pipeline_output.json 재구성 완료: %d개", len(results))

    stored = sum(1 for r in results if r["status"] == "stored")
    hitl = sum(1 for r in results if r["status"] == "hitl_pending")
    error = sum(1 for r in results if r["status"] == "error")
    logger.info("stored=%d, hitl_pending=%d, error=%d", stored, hitl, error)


def main() -> None:
    import os as _os
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8002")
    parser.add_argument(
        "--token",
        default=_os.environ.get("EVAL_AUTH_TOKEN"),
        help="Bearer 토큰. EVAL_AUTH_TOKEN 환경변수로도 설정 가능.",
    )
    args = parser.parse_args()
    asyncio.run(run(args.base_url, token=args.token))


if __name__ == "__main__":
    main()
