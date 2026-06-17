"""
P1-P4 — Neo4j 그래프 DB 성능/정확도 개선 테스트

P1: 인덱스/제약 — 앱 시작 시 Neo4j 인덱스와 유니크 제약이 생성되어야 한다
P2: COVERS 관계 — Document가 Entity를 직접 참조해야 한다 (2-hop 제거)
P3: SHARES_ENTITY 관계 — 같은 Entity를 가진 Document들이 연결되어야 한다
P4: Entity 이름 정규화 — 앞뒤 공백이 제거되어야 한다
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

STAGE6_FILE = Path(__file__).parent.parent / "app" / "pipeline" / "stage6_store.py"
MAIN_FILE = Path(__file__).parent.parent / "app" / "main.py"


# ─── P1: 인덱스/제약 ────────────────────────────────────────────────────────

def test_stage6_has_ensure_indexes_function():
    """stage6_store.py 에 _ensure_neo4j_indexes 함수가 정의되어 있어야 한다."""
    source = STAGE6_FILE.read_text(encoding="utf-8")
    assert "_ensure_neo4j_indexes" in source, (
        "_ensure_neo4j_indexes 함수가 stage6_store.py 에 없음. "
        "Neo4j 인덱스/제약 생성 로직 추가 필요."
    )


def test_stage6_indexes_cover_required_labels():
    """Document, Entity, Category, Chunk 모두 인덱스/제약 대상이어야 한다."""
    source = STAGE6_FILE.read_text(encoding="utf-8")
    for label in ("Document", "Entity", "Category", "Chunk"):
        assert label in source.split("_ensure_neo4j_indexes")[1][:2000], (
            f"_ensure_neo4j_indexes 에 {label} 레이블 인덱스/제약 없음."
        )


def test_main_lifespan_calls_ensure_indexes():
    """main.py lifespan 이 _ensure_neo4j_indexes 를 호출해야 한다."""
    source = MAIN_FILE.read_text(encoding="utf-8")
    assert "_ensure_neo4j_indexes" in source or "ensure_neo4j_indexes" in source, (
        "main.py lifespan 에서 _ensure_neo4j_indexes 호출 없음."
    )


# ─── P2: Document → Entity COVERS 관계 ────────────────────────────────────

def test_stage6_has_covers_relationship():
    """stage6_store.py 에 COVERS 관계 MERGE 쿼리가 있어야 한다."""
    source = STAGE6_FILE.read_text(encoding="utf-8")
    assert "COVERS" in source, (
        "COVERS 관계가 stage6_store.py 에 없음. "
        "Document → Entity 직접 연결 추가 필요."
    )


@pytest.mark.asyncio
async def test_save_to_neo4j_creates_covers_relationship():
    """_save_to_neo4j 가 Document-COVERS-Entity 관계를 생성해야 한다."""
    from app.pipeline.stage6_store import _save_to_neo4j

    run_calls: list[str] = []

    mock_session = AsyncMock()
    mock_session.run = AsyncMock(side_effect=lambda q, **kw: run_calls.append(q))
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_driver = MagicMock()
    mock_driver.session = MagicMock(return_value=mock_session)

    state = {
        "doc_id": "doc-test-001",
        "metadata": {"title": "테스트 문서", "category": "코딩컨벤션"},
        "chunks": [],
        "neo4j_entities": [{"name": "Python", "type": "Technology", "description": ""}],
        "neo4j_relations": [
            {"from_chunk_id": "chunk-001", "entity_name": "Python", "relation_type": "MENTIONS"}
        ],
    }

    with patch("app.pipeline.stage6_store._get_neo4j_driver", return_value=mock_driver):
        await _save_to_neo4j(state)

    covers_queries = [q for q in run_calls if "COVERS" in q]
    assert len(covers_queries) >= 1, (
        f"COVERS 관계 MERGE 쿼리가 실행되지 않음. 실행된 쿼리: {run_calls}"
    )


# ─── P3: Document 간 SHARES_ENTITY 관계 ───────────────────────────────────

def test_stage6_has_shares_entity_relationship():
    """stage6_store.py 에 SHARES_ENTITY 관계 생성 쿼리가 있어야 한다."""
    source = STAGE6_FILE.read_text(encoding="utf-8")
    assert "SHARES_ENTITY" in source, (
        "SHARES_ENTITY 관계가 stage6_store.py 에 없음. "
        "공통 Entity 를 가진 Document 간 연결 추가 필요."
    )


@pytest.mark.asyncio
async def test_save_to_neo4j_creates_shares_entity_relationship():
    """_save_to_neo4j 가 공통 Entity 기반 Document-SHARES_ENTITY-Document 관계를 생성해야 한다."""
    from app.pipeline.stage6_store import _save_to_neo4j

    run_calls: list[str] = []

    mock_session = AsyncMock()
    mock_session.run = AsyncMock(side_effect=lambda q, **kw: run_calls.append(q))
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_driver = MagicMock()
    mock_driver.session = MagicMock(return_value=mock_session)

    state = {
        "doc_id": "doc-test-002",
        "metadata": {"title": "다른 문서", "category": "코딩컨벤션"},
        "chunks": [],
        "neo4j_entities": [{"name": "Python", "type": "Technology", "description": ""}],
        "neo4j_relations": [],
    }

    with patch("app.pipeline.stage6_store._get_neo4j_driver", return_value=mock_driver):
        await _save_to_neo4j(state)

    shares_queries = [q for q in run_calls if "SHARES_ENTITY" in q]
    assert len(shares_queries) >= 1, (
        f"SHARES_ENTITY 관계 MERGE 쿼리가 실행되지 않음. 실행된 쿼리: {run_calls}"
    )


# ─── P4: Entity 이름 정규화 ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_save_to_neo4j_strips_entity_name_whitespace():
    """Entity 이름 앞뒤 공백이 제거되어야 한다."""
    from app.pipeline.stage6_store import _save_to_neo4j

    saved_names: list[str] = []

    async def capture_run(query: str, **kwargs):
        if "MERGE (e:Entity" in query:
            saved_names.append(kwargs.get("name", ""))

    mock_session = AsyncMock()
    mock_session.run = AsyncMock(side_effect=capture_run)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_driver = MagicMock()
    mock_driver.session = MagicMock(return_value=mock_session)

    state = {
        "doc_id": "doc-test-003",
        "metadata": {"title": "테스트", "category": "코딩컨벤션"},
        "chunks": [],
        "neo4j_entities": [
            {"name": "  Python  ", "type": "Technology", "description": ""},
            {"name": "FastAPI ", "type": "Technology", "description": ""},
        ],
        "neo4j_relations": [],
    }

    with patch("app.pipeline.stage6_store._get_neo4j_driver", return_value=mock_driver):
        await _save_to_neo4j(state)

    assert "  Python  " not in saved_names, "Entity 이름 앞뒤 공백 미제거"
    assert "FastAPI " not in saved_names, "Entity 이름 뒤 공백 미제거"
    assert "Python" in saved_names, f"정규화된 이름이 없음. 저장된 이름: {saved_names}"
    assert "FastAPI" in saved_names, f"정규화된 이름이 없음. 저장된 이름: {saved_names}"
