"""
P0 — VALID_CATEGORIES 동적 로드 테스트

현재 버그:
    stage5_metadata_agent.py 와 stage5b_metadata_validate_agent.py 가
    `from _category_definitions import VALID_CATEGORIES` 로 임포트하면
    로컬 바인딩이 생성되어, lifespan 에서 `_category_definitions.VALID_CATEGORIES` 를
    갱신해도 stage5/5b 는 여전히 원래 frozenset 을 본다.

    결과: KB Evolution 으로 "인사정책" 을 추가해도 다음 문서는 또 HITL 트리거.

기대 동작:
    1. `_category_definitions.VALID_CATEGORIES` 를 갱신하면
       stage5_metadata 함수가 `is_new=False` 를 반환해야 한다.
    2. stage5b 규칙 검사도 동일하게 동작해야 한다.
    3. main.py lifespan 이 `get_valid_categories()` 를 호출해
       `_category_definitions.VALID_CATEGORIES` 를 갱신해야 한다.
"""

from __future__ import annotations

import importlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.pipeline._category_definitions as _cat_defs


# ─── 공통 픽스처 ───────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def restore_valid_categories():
    """각 테스트 후 원래 VALID_CATEGORIES 복원."""
    original = _cat_defs.VALID_CATEGORIES
    yield
    _cat_defs.VALID_CATEGORIES = original


# ─── 테스트 1: stage5 — 모듈 변수 갱신 시 is_new 변경 ─────────────────────────

@pytest.mark.asyncio
async def test_stage5_new_category_recognized_after_module_update():
    """
    _cat_defs.VALID_CATEGORIES 를 갱신하면 stage5 가 is_new=False 를 반환해야 한다.

    현재 구현은 로컬 바인딩을 사용하므로 이 테스트는 RED 다.
    """
    from app.pipeline.stage5_metadata_agent import stage5_metadata

    # DB 에 "인사정책" 이 추가된 상태 시뮬레이션
    _cat_defs.VALID_CATEGORIES = _cat_defs.VALID_CATEGORIES | {"인사정책"}

    mock_metadata = {
        "title": "인사 규정 문서",
        "category": "인사정책",
        "category_reasoning": "인사 규정에 관한 문서",
        "category_alternatives": ["기타"],
        "team": None,
        "author": None,
        "tags": [],
        "source": "upload",
    }

    with patch(
        "app.pipeline.stage5_metadata_agent._extract_metadata",
        new=AsyncMock(return_value=(mock_metadata, [])),
    ):
        state = {
            "doc_id": "test-doc-001",
            "validated_markdown": "# 인사 규정\n\n회사 인사 규정입니다.",
            "chunks": [],
        }
        result = await stage5_metadata(state)

    # 핵심 assertion: DB 에 추가된 카테고리는 is_new=False 여야 한다
    assert result["category_is_new"] is False, (
        f"category_is_new={result['category_is_new']} — "
        "_cat_defs.VALID_CATEGORIES 를 갱신했는데도 stage5 가 is_new=True 반환. "
        "stage5 가 모듈 변수 대신 로컬 바인딩을 사용 중."
    )


# ─── 테스트 2: stage5b — 모듈 변수 갱신 시 규칙 검사 통과 ─────────────────────

@pytest.mark.asyncio
async def test_stage5b_new_category_passes_rule_check_after_module_update():
    """
    _cat_defs.VALID_CATEGORIES 를 갱신하면 stage5b 규칙 검사에서 HITL 이 트리거되지 않아야 한다.

    현재 구현은 로컬 바인딩을 사용하므로 이 테스트는 RED 다.
    """
    from app.pipeline.stage5b_metadata_validate_agent import stage5b_metadata_validate

    # DB 에 "인사정책" 이 추가된 상태 시뮬레이션
    _cat_defs.VALID_CATEGORIES = _cat_defs.VALID_CATEGORIES | {"인사정책"}

    state = {
        "doc_id": "test-doc-001",
        "validated_markdown": "# 인사 규정\n\n회사 인사 규정입니다.",
        "metadata": {
            "title": "인사 규정 문서",
            "category": "인사정책",
            "tags": [],
        },
        "neo4j_entities": [],
        "category_is_new": False,
        "category_reasoning": "",
        "category_alternatives": [],
    }

    with patch(
        "app.pipeline.stage5b_metadata_validate_agent._validate_with_llm",
        new=AsyncMock(return_value=(0.9, [])),
    ):
        result = await stage5b_metadata_validate(state)

    # 핵심 assertion: DB 추가 카테고리는 규칙 검사에서 HITL 트리거 금지
    assert result.get("hitl_required") is False, (
        f"hitl_required={result.get('hitl_required')} — "
        "stage5b 가 '인사정책' 을 유효하지 않은 카테고리로 판정. "
        "VALID_CATEGORIES 로컬 바인딩 문제."
    )


# ─── 테스트 3: lifespan — get_valid_categories 호출 후 모듈 변수 갱신 ──────────

@pytest.mark.asyncio
async def test_lifespan_updates_valid_categories_from_db():
    """
    main.py lifespan 이 DB 에서 카테고리를 읽어 _cat_defs.VALID_CATEGORIES 를
    갱신해야 한다.

    현재 lifespan 에는 이 코드가 없으므로 이 테스트는 RED 다.
    """
    db_categories = frozenset({"코딩컨벤션", "아키텍처", "온보딩", "보안", "배포", "기타", "인사정책"})

    mock_session_factory = MagicMock()

    with patch(
        "app.categories_db.get_valid_categories",
        new=AsyncMock(return_value=db_categories),
    ) as mock_get, patch(
        "shared.db._AsyncSessionFactory",
        mock_session_factory,
    ), patch(
        "app.storage.get_storage",
        return_value=MagicMock(),
    ), patch(
        "app.pipeline.graph.build_pipeline",
        return_value=MagicMock(),
    ), patch(
        "shared.logging.configure_logging",
    ):
        # lifespan 직접 실행
        from app.main import lifespan
        mock_app = MagicMock()
        async with lifespan(mock_app):
            pass

    # 핵심 assertion: lifespan 종료 후 VALID_CATEGORIES 에 "인사정책" 포함
    assert "인사정책" in _cat_defs.VALID_CATEGORIES, (
        "lifespan 이 get_valid_categories() 를 호출해 "
        "_cat_defs.VALID_CATEGORIES 를 갱신하지 않음."
    )


# ─── 테스트 4: 기존 기본 카테고리는 항상 유효 ──────────────────────────────────

def test_default_categories_always_valid():
    """기존 6개 카테고리는 변경 전후 항상 VALID_CATEGORIES 에 포함되어야 한다."""
    defaults = {"코딩컨벤션", "아키텍처", "온보딩", "보안", "배포", "기타"}
    assert defaults.issubset(_cat_defs.VALID_CATEGORIES), (
        f"기본 카테고리가 VALID_CATEGORIES 에 없음: "
        f"{defaults - _cat_defs.VALID_CATEGORIES}"
    )
