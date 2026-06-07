"""
TDD — HITL reject 시 파생 GCS 파일 삭제

정책:
  DELETE  images/{doc_id}/page_*.png   (페이지 이미지 — 용량 큼)
  DELETE  markdown/{doc_id}/*          (파생 마크다운)
  KEEP    originals/{doc_id}.*         (원본 — 재처리 가능성)
  KEEP    documents 레코드              (감사 이력)
"""

import re
from pathlib import Path

M0_ROOT         = Path(__file__).parent.parent
STORAGE_FILE    = M0_ROOT / "app" / "storage.py"
HITL_ROUTE_FILE = M0_ROOT / "app" / "routes" / "hitl_routes.py"


# ── Storage 인터페이스 ────────────────────────────────────────────────────────

def test_storage_has_delete_method():
    """Storage ABC에 delete(path) 메서드가 있어야 한다."""
    source = STORAGE_FILE.read_text(encoding="utf-8")
    assert re.search(r"async def delete\s*\(", source), (
        "Storage must define 'async def delete(self, path)'"
    )


def test_storage_has_list_prefix_method():
    """Storage ABC에 list_prefix(prefix) 메서드가 있어야 한다."""
    source = STORAGE_FILE.read_text(encoding="utf-8")
    assert re.search(r"async def list_prefix\s*\(", source), (
        "Storage must define 'async def list_prefix(self, prefix)'"
    )


# ── reject 엔드포인트 동작 ────────────────────────────────────────────────────

def test_reject_calls_delete_images():
    """reject_hitl이 images/{doc_id}/ 경로를 삭제해야 한다."""
    source = HITL_ROUTE_FILE.read_text(encoding="utf-8")
    assert re.search(r"images/.*doc_id", source), (
        "reject_hitl must delete 'images/{doc_id}/' page images from storage"
    )


def test_reject_calls_delete_markdown():
    """reject_hitl이 markdown/{doc_id}/ 경로를 삭제해야 한다."""
    source = HITL_ROUTE_FILE.read_text(encoding="utf-8")
    assert re.search(r"markdown/.*doc_id", source), (
        "reject_hitl must delete 'markdown/{doc_id}/' files from storage"
    )


def test_reject_does_not_delete_originals():
    """reject_hitl이 originals/ 경로를 삭제 대상 prefix로 사용하면 안 된다."""
    source = HITL_ROUTE_FILE.read_text(encoding="utf-8")
    reject_fn = _extract_reject_function(source)
    # 실제 prefix 목록에 originals/ 가 포함되면 안 됨
    # (docstring/주석에 언급은 허용)
    assert not re.search(r'["\']originals/.*?["\']', reject_fn), (
        "reject_hitl must NOT include 'originals/' in deletion prefix list"
    )


def test_reject_uses_list_prefix_then_delete():
    """reject_hitl이 list_prefix로 파일 목록을 조회 후 delete 해야 한다."""
    source = HITL_ROUTE_FILE.read_text(encoding="utf-8")
    assert "list_prefix" in source, (
        "reject_hitl must use list_prefix() to enumerate files before deleting"
    )
    assert re.search(r"\.delete\(", source), (
        "reject_hitl must call storage.delete() to remove files"
    )


def _extract_reject_function(source: str) -> str:
    """reject_hitl 함수 본문만 추출."""
    start = source.find("async def reject_hitl")
    if start == -1:
        return source
    # 다음 @router 또는 async def 까지
    next_fn = re.search(r"\n@router|\nasync def ", source[start + 1:])
    end = start + 1 + next_fn.start() if next_fn else len(source)
    return source[start:end]
