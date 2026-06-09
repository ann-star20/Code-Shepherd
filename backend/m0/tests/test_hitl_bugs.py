"""
RED reproducers for two HITL bugs:

Bug 1 — page-images SQL syntax error (page-images 500)
  :doc_id::uuid in SQLAlchemy text() is misinterpreted as ":doc_id:" + ":uuid"
  → asyncpg raises PostgresSyntaxError on the colon before uuid

Bug 2 — ItemDetail splitData state bleed
  ItemDetail renders without key={item.queue_id}, so React reuses
  the component instance across item selections. A "Markdown 로드 실패"
  error from item A persists when the user selects a new item.
"""

import re
from pathlib import Path

# Repo root is 3 levels up from this test file:
# backend/m0/tests/test_hitl_bugs.py -> backend/m0/tests -> backend/m0 -> backend -> repo
REPO_ROOT = Path(__file__).parent.parent.parent.parent
M0_ROOT   = Path(__file__).parent.parent

HITL_ROUTE_FILE    = M0_ROOT / "app" / "routes" / "hitl_routes.py"
HITL_QUEUE_TSX     = REPO_ROOT / "frontend" / "src" / "components" / "HitlQueue.tsx"

# ── Bug 1: SQL syntax check ──────────────────────────────────────────────────

INLINE_CAST_RE = re.compile(r":doc_id::uuid", re.MULTILINE)
SAFE_CAST_RE   = re.compile(
    r"CAST\(:doc_id\s+AS\s+uuid\)|c\.doc_id::text\s*=\s*:doc_id",
    re.MULTILINE,
)


def test_page_images_sql_no_inline_cast() -> None:
    """`:doc_id::uuid` must NOT appear in hitl_routes.py.

    SQLAlchemy text() treats the colon in `::uuid` as the start of a
    second parameter token, causing asyncpg.PostgresSyntaxError → HTTP 500.
    """
    source = HITL_ROUTE_FILE.read_text(encoding="utf-8")
    assert not INLINE_CAST_RE.search(source), (
        f"Found ':doc_id::uuid' in {HITL_ROUTE_FILE.name} — "
        "use CAST(:doc_id AS uuid) or c.doc_id::text = :doc_id instead."
    )


def test_page_images_sql_uses_safe_cast() -> None:
    """After the fix, the page-images query must use a safe cast form."""
    source = HITL_ROUTE_FILE.read_text(encoding="utf-8")
    assert SAFE_CAST_RE.search(source), (
        "page-images query must cast doc_id safely: "
        "CAST(:doc_id AS uuid) or c.doc_id::text = :doc_id"
    )


# ── Bug 2: ItemDetail key prop ───────────────────────────────────────────────

KEY_RE    = re.compile(r"<ItemDetail\b[^>]*key=\{[^>]*queue_id[^>]*\}", re.DOTALL)


def test_item_detail_has_queue_id_key() -> None:
    """ItemDetail must have key={selected.queue_id} (or queue_id variant).

    Without a key, React reuses the same component instance when the user
    selects a different item. The splitData state (including a previous
    'Markdown 로드 실패' error) bleeds over to the newly selected item.
    """
    if not HITL_QUEUE_TSX.exists():
        import pytest
        pytest.skip(f"Frontend file not found: {HITL_QUEUE_TSX}")

    source = HITL_QUEUE_TSX.read_text(encoding="utf-8")
    assert KEY_RE.search(source), (
        "<ItemDetail> must include key={{selected.queue_id}} so React "
        "remounts the component on item change, resetting splitData state."
    )
