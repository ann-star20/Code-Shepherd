"""TDD — HITL KB Evolution 엔드포인트 테스트.

GET  /hitl/queue/{id}/suggest-category  → AI 카테고리 제안 3개
POST /hitl/queue/{id}/apply-category    → 카테고리 DB 추가 + 파이프라인 재시작
"""

from __future__ import annotations

import pytest
import module_0_kms.hitl_api as hitl_api
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

class _FakeRow(dict):
    pass


class _AcquireCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *_):
        return False


class _FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _AcquireCtx(self._conn)


def _make_hitl_row(
    queue_id: str = "aaaaaaaa-0000-0000-0000-000000000001",
    doc_id: str   = "bbbbbbbb-0000-0000-0000-000000000001",
    stage: str    = "stage5b_metadata_validate",
    issues: dict  | None = None,
) -> _FakeRow:
    import json
    return _FakeRow(
        queue_id=queue_id,
        doc_id=doc_id,
        stage=stage,
        issues=json.dumps(issues or {
            "issues": ["새 카테고리 제안: 'NCS교육'"],
            "category_reasoning": "NCS 기반 교육 자료입니다.",
            "category_alternatives": ["아키텍처", "온보딩"],
        }),
        status="pending",
        reason="새 카테고리 감지",
    )


# ---------------------------------------------------------------------------
# GET /hitl/queue/{id}/suggest-category
# ---------------------------------------------------------------------------

class TestSuggestCategory:

    @pytest.fixture
    def fake_conn(self):
        class _Conn:
            async def fetchrow(self, *a, **_): return _make_hitl_row()
        return _Conn()

    async def test_suggest_returns_list_of_strings(self, monkeypatch, fake_conn):
        """suggest-category가 문자열 리스트를 반환해야 한다."""
        from module_0_kms.hitl_api import suggest_category_for_hitl

        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(fake_conn))
        result = await suggest_category_for_hitl("aaaaaaaa-0000-0000-0000-000000000001")
        assert isinstance(result, dict)
        assert "suggested" in result
        assert isinstance(result["suggested"], list)
        assert all(isinstance(s, str) for s in result["suggested"])

    async def test_suggest_includes_reasoning(self, monkeypatch, fake_conn):
        """suggest-category 응답에 AI 추론 근거가 포함되어야 한다."""
        from module_0_kms.hitl_api import suggest_category_for_hitl

        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(fake_conn))
        result = await suggest_category_for_hitl("aaaaaaaa-0000-0000-0000-000000000001")
        assert "reasoning" in result or "category_reasoning" in result

    async def test_suggest_includes_alternatives(self, monkeypatch, fake_conn):
        """suggest-category 응답에 기존 카테고리 차선책이 포함되어야 한다."""
        from module_0_kms.hitl_api import suggest_category_for_hitl

        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(fake_conn))
        result = await suggest_category_for_hitl("aaaaaaaa-0000-0000-0000-000000000001")
        assert "alternatives" in result or "category_alternatives" in result


# ---------------------------------------------------------------------------
# POST /hitl/queue/{id}/apply-category
# ---------------------------------------------------------------------------

class TestApplyCategory:

    async def test_apply_category_adds_to_db(self, monkeypatch):
        """apply-category가 categories 테이블에 새 카테고리를 INSERT해야 한다."""
        from module_0_kms.hitl_api import apply_category_from_hitl

        executed = []

        class _Conn:
            async def fetchrow(self, *a, **_):
                return _make_hitl_row()

            async def execute(self, query, *a, **_):
                executed.append(query)

        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(_Conn()))

        with patch("kms.hitl_api._reprocess_document", AsyncMock()):
            await apply_category_from_hitl(
                queue_id="aaaaaaaa-0000-0000-0000-000000000001",
                category="NCS교육",
                description="NCS 기반 교육 커리큘럼",
            )

        assert any("INSERT" in q.upper() or "categories" in q.lower() for q in executed), (
            f"categories INSERT 없음. 실행된 쿼리: {executed}"
        )

    async def test_apply_category_triggers_reprocess(self, monkeypatch):
        """apply-category 후 파이프라인 재처리가 시작되어야 한다."""
        from module_0_kms.hitl_api import apply_category_from_hitl

        class _Conn:
            async def fetchrow(self, *a, **_): return _make_hitl_row()
            async def execute(self, *a, **_): pass

        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(_Conn()))

        reprocess_called = []
        async def fake_reprocess(*a, **kw):
            reprocess_called.append(kw.get("corrected_category") or a)

        with patch("kms.hitl_api._reprocess_document", fake_reprocess):
            await apply_category_from_hitl(
                queue_id="aaaaaaaa-0000-0000-0000-000000000001",
                category="NCS교육",
                description="",
            )

        assert reprocess_called, "apply_category_from_hitl 후 재처리 미시작"
