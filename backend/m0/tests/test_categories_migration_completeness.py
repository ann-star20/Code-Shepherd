"""
A4 — categories 마이그레이션 완전성 테스트

_category_definitions.CATEGORY_DEFINITIONS 의 모든 키가
Alembic 마이그레이션 파일의 INSERT 시드에 포함되어 있는지 검증한다.

버그 시나리오:
    카테고리 키를 _category_definitions.py 에 추가했지만
    마이그레이션 시드가 누락되면, lifespan 에서 DB를 로드할 때
    해당 카테고리가 VALID_CATEGORIES 에서 빠져 HITL 이 계속 트리거된다.
"""

from __future__ import annotations

import os
import re


def _collect_seeded_category_names() -> set[str]:
    """Alembic 마이그레이션 파일 전체에서 INSERT된 카테고리 이름을 수집한다."""
    migrations_dir = os.path.join(
        os.path.dirname(__file__), "..", "alembic", "versions"
    )
    seeded: set[str] = set()
    for filename in sorted(os.listdir(migrations_dir)):
        if not filename.endswith(".py"):
            continue
        filepath = os.path.join(migrations_dir, filename)
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
        # ('카테고리명', '설명') 형태의 INSERT VALUES 항목 추출
        matches = re.findall(r"\('([^']+)',\s*'[^']*'\)", content)
        seeded.update(matches)
    return seeded


def test_all_pipeline_categories_seeded_in_migrations():
    """
    파이프라인 카테고리 키가 모두 Alembic 마이그레이션 시드에 존재해야 한다.

    현재 AI_ML, 프로젝트관리, 코드성능검증 이 누락되어 있으므로 RED.
    """
    from app.pipeline._category_definitions import CATEGORY_DEFINITIONS

    pipeline_keys = set(CATEGORY_DEFINITIONS.keys())
    seeded_names = _collect_seeded_category_names()

    missing = pipeline_keys - seeded_names
    assert not missing, (
        f"마이그레이션 시드에 없는 카테고리 {len(missing)}개: {missing}\n"
        "→ 새 Alembic 마이그레이션에 INSERT 시드를 추가하세요."
    )


def test_seeded_categories_not_empty():
    """마이그레이션 파일에서 최소 1개 이상의 카테고리가 추출되어야 한다."""
    seeded = _collect_seeded_category_names()
    assert len(seeded) >= 6, f"시드 카테고리가 너무 적음: {seeded}"
