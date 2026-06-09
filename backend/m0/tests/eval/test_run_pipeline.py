"""
run_pipeline.py TDD 테스트

RED: run_pipeline.py가 없으므로 import 실패 → 전부 실패
GREEN: run_pipeline.py 구현 후 통과
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

EVAL_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# 테스트 1: golden_dataset 로드
# ---------------------------------------------------------------------------

def test_load_eval_docs_returns_only_files_that_exist():
    """golden_dataset의 문서 중 실제 파일이 있는 것만 반환한다."""
    from tests.eval.run_pipeline import load_eval_docs

    docs = load_eval_docs()
    assert len(docs) > 0
    for doc in docs:
        assert "id" in doc
        assert "file" in doc
        assert "file_type" in doc
        file_path = EVAL_DIR / doc["file"]
        assert file_path.exists(), f"파일 없음: {file_path}"


# ---------------------------------------------------------------------------
# 테스트 2: 문서 업로드 → doc_id 반환
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_upload_document_returns_doc_id():
    """POST /kms/upload 호출 시 doc_id를 반환한다."""
    from tests.eval.run_pipeline import upload_document

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "doc_id": "test-doc-id-001",
        "status": "processing",
        "message": "파이프라인 시작",
    }

    with patch("httpx.AsyncClient.post", return_value=mock_response):
        doc_id = await upload_document(
            base_url="http://localhost:8000",
            file_path=EVAL_DIR / "documents/md/md_01_tech_intro.md",
        )

    assert doc_id == "test-doc-id-001"


# ---------------------------------------------------------------------------
# 테스트 3: 상태 폴링 → stored 완료
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_poll_status_returns_stored():
    """GET /kms/status/{doc_id}가 stored를 반환하면 종료한다."""
    from tests.eval.run_pipeline import poll_until_done

    responses = [
        {"status": "processing", "quality_score": None},
        {"status": "processing", "quality_score": None},
        {"status": "stored",     "quality_score": 0.92},
    ]
    call_count = 0

    async def mock_get(*args, **kwargs):
        nonlocal call_count
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = responses[min(call_count, len(responses) - 1)]
        call_count += 1
        return resp

    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        result = await poll_until_done(
            base_url="http://localhost:8000",
            doc_id="test-doc-id-001",
            poll_interval=0,
            max_retries=5,
        )

    assert result["status"] == "stored"
    assert result["quality_score"] == 0.92


# ---------------------------------------------------------------------------
# 테스트 4: 상태 폴링 → hitl_pending도 완료로 처리
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_poll_status_accepts_hitl_pending():
    """hitl_pending 상태도 완료로 처리한다."""
    from tests.eval.run_pipeline import poll_until_done

    async def mock_get(*args, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"status": "hitl_pending", "quality_score": 0.65}
        return resp

    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        result = await poll_until_done(
            base_url="http://localhost:8000",
            doc_id="test-doc-id-001",
            poll_interval=0,
            max_retries=5,
        )

    assert result["status"] == "hitl_pending"


# ---------------------------------------------------------------------------
# 테스트 5: 폴링 타임아웃
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_poll_status_timeout_raises():
    """max_retries 초과 시 TimeoutError를 발생시킨다."""
    from tests.eval.run_pipeline import poll_until_done

    async def mock_get(*args, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"status": "processing", "quality_score": None}
        return resp

    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        with pytest.raises(TimeoutError):
            await poll_until_done(
                base_url="http://localhost:8000",
                doc_id="test-doc-id-001",
                poll_interval=0,
                max_retries=3,
            )


# ---------------------------------------------------------------------------
# 테스트 6: 메타데이터 수집
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_metadata_returns_title_category_tags():
    """GET /kms/docs/{doc_id}/metadata에서 title/category/tags를 반환한다."""
    from tests.eval.run_pipeline import fetch_metadata

    async def mock_get(*args, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "doc_id": "test-doc-id-001",
            "title": "대규모 언어 모델(LLM) 기술 개요",
            "category": "AI_ML",
            "tags": ["LLM", "트랜스포머"],
            "source": "upload",
            "file_type": "md",
        }
        return resp

    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        meta = await fetch_metadata(
            base_url="http://localhost:8000",
            doc_id="test-doc-id-001",
        )

    assert meta["title"] == "대규모 언어 모델(LLM) 기술 개요"
    assert meta["category"] == "AI_ML"
    assert "LLM" in meta["tags"]


# ---------------------------------------------------------------------------
# 테스트 7: pipeline_output.json 형식 검증
# ---------------------------------------------------------------------------

def test_build_output_entry_has_required_fields():
    """pipeline_output.json 항목이 run_eval.py가 읽을 수 있는 형식인지 확인한다."""
    from tests.eval.run_pipeline import build_output_entry

    entry = build_output_entry(
        golden_id="md_01",
        doc_id="uuid-001",
        title="테스트 제목",
        category="AI_ML",
        tags=["LLM", "GPT"],
        entities={},
        quality_score=0.9,
        status="stored",
    )

    assert entry["golden_id"] == "md_01"
    assert entry["doc_id"] == "uuid-001"
    assert entry["title"] == "테스트 제목"
    assert entry["category"] == "AI_ML"
    assert entry["tags"] == ["LLM", "GPT"]
    assert entry["entities"] == {}
    assert entry["quality_score"] == 0.9
    assert entry["status"] == "stored"
