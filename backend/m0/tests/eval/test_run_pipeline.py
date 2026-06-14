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
# 테스트 6b: fetch_metadata → child_chunk_count (P0 TDD)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_metadata_returns_child_chunk_count():
    """/details 응답의 chunks 목록에서 child 타입 개수를 child_chunk_count로 반환한다."""
    from tests.eval.run_pipeline import fetch_metadata

    async def mock_get(*args, **kwargs):
        url = args[0] if args else ""
        resp = MagicMock()
        resp.status_code = 200
        if "/metadata" in url:
            resp.json.return_value = {
                "doc_id": "test-doc-id-001",
                "title": "테스트 문서",
                "category": "AI_ML",
                "tags": [],
                "source": "upload",
                "file_type": "md",
            }
        elif "/entities" in url:
            resp.json.return_value = {"entities": []}
        elif "/details" in url:
            resp.json.return_value = {
                "quality_score": 0.9,
                "chunks": [
                    {"chunk_type": "parent"},
                    {"chunk_type": "child"},
                    {"chunk_type": "child"},
                    {"chunk_type": "child"},
                ],
            }
        else:
            resp.json.return_value = {}
        return resp

    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        meta = await fetch_metadata(
            base_url="http://localhost:8000",
            doc_id="test-doc-id-001",
        )

    assert "child_chunk_count" in meta, (
        "fetch_metadata()가 'child_chunk_count' 키를 반환하지 않음 — run_pipeline.py 수정 필요"
    )
    assert meta["child_chunk_count"] == 3, (
        f"child 청크 수 불일치: 예상=3, 실제={meta.get('child_chunk_count')}"
    )


@pytest.mark.asyncio
async def test_fetch_metadata_child_chunk_count_none_when_details_fails():
    """/details 실패 시 child_chunk_count는 None이어야 한다."""
    from tests.eval.run_pipeline import fetch_metadata

    async def mock_get(*args, **kwargs):
        url = args[0] if args else ""
        resp = MagicMock()
        if "/metadata" in url:
            resp.status_code = 200
            resp.json.return_value = {"title": "T", "category": "C", "tags": []}
        elif "/entities" in url:
            resp.status_code = 200
            resp.json.return_value = {"entities": []}
        else:
            resp.status_code = 500
        return resp

    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        meta = await fetch_metadata(
            base_url="http://localhost:8000",
            doc_id="test-doc-id-001",
        )

    assert meta.get("child_chunk_count") is None, (
        f"details 실패 시 child_chunk_count는 None이어야 함. 실제: {meta.get('child_chunk_count')}"
    )


# ---------------------------------------------------------------------------
# 테스트 6c: build_output_entry → child_chunk_count (P0 TDD)
# ---------------------------------------------------------------------------

def test_build_output_entry_includes_child_chunk_count():
    """build_output_entry()가 child_chunk_count를 출력에 포함해야 한다."""
    from tests.eval.run_pipeline import build_output_entry

    entry = build_output_entry(
        golden_id="md_01",
        doc_id="uuid-001",
        file_type="md",
        title="테스트",
        category="AI_ML",
        tags=[],
        entities={},
        quality_score=0.9,
        status="stored",
        child_chunk_count=5,
    )

    assert "child_chunk_count" in entry, (
        "build_output_entry() 반환값에 'child_chunk_count' 키 없음 — run_pipeline.py 수정 필요"
    )
    assert entry["child_chunk_count"] == 5


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


# ---------------------------------------------------------------------------
# T1: fetch_metadata → parsing_time_ms, parser_used (Stage 1 성능)
# ---------------------------------------------------------------------------

def _make_url_aware_mock(details_extra: dict | None = None):
    """URL 패턴별로 다른 응답을 반환하는 mock GET 함수."""
    async def mock_get(*args, **kwargs):
        url = args[0] if args else ""
        resp = MagicMock()
        resp.status_code = 200
        if "/metadata" in url:
            resp.json.return_value = {
                "doc_id": "test-id",
                "title": "테스트", "category": "AI_ML", "tags": [], "source": "upload",
            }
        elif "/entities" in url:
            resp.json.return_value = {"entities": []}
        elif "/details" in url:
            details = {
                "quality_score": 0.9,
                "chunks": [{"chunk_type": "child"}],
                "parsing_time_ms": 5200,
                "parser_used": "pymupdf",
                "stage5_latency_ms": 8100,
            }
            if details_extra:
                details.update(details_extra)
            resp.json.return_value = details
        else:
            resp.json.return_value = {}
        return resp
    return mock_get


@pytest.mark.asyncio
async def test_fetch_metadata_returns_parsing_time_ms():
    """/details 응답에서 parsing_time_ms를 수집해야 한다 (T1)."""
    from tests.eval.run_pipeline import fetch_metadata

    with patch("httpx.AsyncClient.get", side_effect=_make_url_aware_mock()):
        meta = await fetch_metadata(base_url="http://localhost:8000", doc_id="test-id")

    assert "parsing_time_ms" in meta, (
        f"fetch_metadata()에 parsing_time_ms 없음. 키: {sorted(meta.keys())}"
    )
    assert meta["parsing_time_ms"] == 5200


@pytest.mark.asyncio
async def test_fetch_metadata_returns_parser_used():
    """/details 응답에서 parser_used를 수집해야 한다 (T1)."""
    from tests.eval.run_pipeline import fetch_metadata

    with patch("httpx.AsyncClient.get", side_effect=_make_url_aware_mock()):
        meta = await fetch_metadata(base_url="http://localhost:8000", doc_id="test-id")

    assert "parser_used" in meta, (
        f"fetch_metadata()에 parser_used 없음. 키: {sorted(meta.keys())}"
    )
    assert meta["parser_used"] == "pymupdf"


# ---------------------------------------------------------------------------
# T5: fetch_metadata → stage5_latency_ms (Stage 5 LLM latency)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_metadata_returns_stage5_latency_ms():
    """/details 응답에서 stage5_latency_ms를 수집해야 한다 (T5)."""
    from tests.eval.run_pipeline import fetch_metadata

    with patch("httpx.AsyncClient.get", side_effect=_make_url_aware_mock()):
        meta = await fetch_metadata(base_url="http://localhost:8000", doc_id="test-id")

    assert "stage5_latency_ms" in meta, (
        f"fetch_metadata()에 stage5_latency_ms 없음. 키: {sorted(meta.keys())}"
    )
    assert meta["stage5_latency_ms"] == 8100


@pytest.mark.asyncio
async def test_fetch_metadata_stage5_latency_ms_none_when_absent():
    """/details에 stage5_latency_ms 없을 때 None 반환해야 한다."""
    from tests.eval.run_pipeline import fetch_metadata

    with patch("httpx.AsyncClient.get", side_effect=_make_url_aware_mock({"stage5_latency_ms": None})):
        meta = await fetch_metadata(base_url="http://localhost:8000", doc_id="test-id")

    assert meta.get("stage5_latency_ms") is None


# ---------------------------------------------------------------------------
# T1: build_output_entry → parsing_time_ms, parser_used
# ---------------------------------------------------------------------------

def test_build_output_entry_includes_parsing_time_ms():
    """build_output_entry()는 parsing_time_ms를 output에 포함해야 한다 (T1)."""
    from tests.eval.run_pipeline import build_output_entry

    entry = build_output_entry(
        golden_id="md_01", doc_id="test-id", file_type="md",
        title="테스트", category="AI_ML", tags=[], entities={},
        quality_score=0.9, status="stored",
        parsing_time_ms=5200,
    )

    assert "parsing_time_ms" in entry
    assert entry["parsing_time_ms"] == 5200


def test_build_output_entry_includes_parser_used():
    """build_output_entry()는 parser_used를 output에 포함해야 한다 (T1)."""
    from tests.eval.run_pipeline import build_output_entry

    entry = build_output_entry(
        golden_id="md_01", doc_id="test-id", file_type="md",
        title="테스트", category="AI_ML", tags=[], entities={},
        quality_score=0.9, status="stored",
        parser_used="gemini",
    )

    assert "parser_used" in entry
    assert entry["parser_used"] == "gemini"
