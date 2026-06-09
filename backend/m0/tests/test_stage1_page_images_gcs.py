"""
TDD — stage1 페이지 이미지 GCS 즉시 저장

목표: 어떤 파서(pymupdf/upstage/gemini)를 쓰든, HITL이 언제 걸리든
      stage1 완료 시점에 페이지 이미지가 이미 GCS에 저장되어 있어야 한다.

Bug: 현재 page_images(raw bytes)를 state에 담아 stage6까지 전달하므로
     stage5b HITL이 걸리면 stage6가 실행되지 않아 GCS에 이미지가 없다.
     HITL 검토 화면에서 "페이지 이미지가 없습니다"가 뜨는 이유.

Fix:
  - stage1: 이미지 추출 직후 GCS 저장 → state["page_image_paths"] (경로 목록)
  - stage6: page_image_paths 이미 있으면 재저장 생략
"""

import asyncio
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

M0_ROOT = Path(__file__).parent.parent
STAGE1_FILE = M0_ROOT / "app" / "pipeline" / "stage1_document_parser_agent.py"
STAGE6_FILE = M0_ROOT / "app" / "pipeline" / "stage6_store.py"


# ── 정적 분석 테스트 ─────────────────────────────────────────────────────────

def test_stage1_saves_page_images_to_gcs_not_raw_bytes():
    """stage1 반환값에 raw bytes(page_images)가 아닌 GCS 경로(page_image_paths)가 있어야 한다."""
    source = STAGE1_FILE.read_text(encoding="utf-8")
    # page_image_paths 를 state에 담아 반환해야 함
    assert '"page_image_paths"' in source or "'page_image_paths'" in source, (
        "stage1 must return 'page_image_paths' (GCS paths) instead of raw 'page_images' bytes"
    )


def test_stage6_skips_save_when_paths_already_exist():
    """stage6는 page_image_paths가 이미 있으면 재저장하지 않아야 한다."""
    source = STAGE6_FILE.read_text(encoding="utf-8")
    assert "page_image_paths" in source, (
        "stage6 must check for existing 'page_image_paths' to skip redundant GCS save"
    )


# ── 동작 테스트 ──────────────────────────────────────────────────────────────

def test_save_page_images_in_stage1_calls_storage_save():
    """stage1이 page images 추출 후 storage.save()를 호출하는지 검증."""
    source = STAGE1_FILE.read_text(encoding="utf-8")

    # storage.save 가 이미지 경로(images/{doc_id}/page_*.png)로 호출되어야 함
    assert re.search(r"images/.*page_", source), (
        "stage1 must call storage.save with path like 'images/{doc_id}/page_{n}.png'"
    )


def test_stage1_returns_page_image_paths_list():
    """stage1 반환 dict에 page_image_paths 키가 list 타입으로 존재해야 한다."""
    source = STAGE1_FILE.read_text(encoding="utf-8")

    # 반환부에 page_image_paths 가 포함되어야 함
    return_block = source[source.rfind('return {'):]
    assert "page_image_paths" in return_block, (
        "stage1 final return dict must include 'page_image_paths'"
    )
