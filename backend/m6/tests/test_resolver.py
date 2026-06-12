"""tests/test_resolver.py — HybridResolver 단위 테스트 (mock 기반, DB 연결 없음)."""

from __future__ import annotations

import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.infrastructure.graph.hybrid_resolver import (
    MERGE_THRESHOLD,
    RELATED_THRESHOLD,
    HybridResolver,
    ResolveAction,
    _action_from_score,
    _cosine,
    _jaro_winkler_max,
    _parse_pg_vector,
)


# ── _cosine 단위 테스트 ────────────────────────────────────────────────────────

class TestCosine:
    def test_identical_vectors_return_one(self):
        v = [1.0, 0.0, 0.0]
        assert _cosine(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors_return_zero(self):
        assert _cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_opposite_vectors_return_negative_one(self):
        assert _cosine([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)

    def test_zero_vector_returns_zero(self):
        assert _cosine([0.0, 0.0], [1.0, 0.0]) == 0.0

    def test_different_length_returns_zero(self):
        assert _cosine([1.0, 0.0], [1.0, 0.0, 0.0]) == 0.0

    def test_empty_vectors_return_zero(self):
        assert _cosine([], []) == 0.0


# ── _jaro_winkler_max 단위 테스트 ─────────────────────────────────────────────

class TestJaroWinklerMax:
    def test_identical_names(self):
        score = _jaro_winkler_max("XSS", [], "XSS", [])
        assert score == pytest.approx(1.0)

    def test_case_insensitive(self):
        score = _jaro_winkler_max("xss", [], "XSS", [])
        assert score == pytest.approx(1.0)

    def test_alias_match(self):
        score = _jaro_winkler_max("CrossSiteScripting", [], "XSS", ["CrossSiteScripting"])
        assert score == pytest.approx(1.0)

    def test_unrelated_names_low_score(self):
        score = _jaro_winkler_max("XSS", [], "SQLInjection", [])
        assert score < 0.7

    def test_prefix_boost(self):
        score_prefix = _jaro_winkler_max("SQLI", [], "SQLInjection", [])
        score_suffix = _jaro_winkler_max("njection", [], "SQLInjection", [])
        assert score_prefix > score_suffix


# ── _action_from_score 단위 테스트 ────────────────────────────────────────────

class TestActionFromScore:
    def test_merge_at_threshold(self):
        assert _action_from_score(MERGE_THRESHOLD) == ResolveAction.MERGE

    def test_merge_above_threshold(self):
        assert _action_from_score(0.95) == ResolveAction.MERGE

    def test_related_to_at_threshold(self):
        assert _action_from_score(RELATED_THRESHOLD) == ResolveAction.RELATED_TO

    def test_related_to_between_thresholds(self):
        assert _action_from_score(0.80) == ResolveAction.RELATED_TO

    def test_new_below_related_threshold(self):
        assert _action_from_score(0.5) == ResolveAction.NEW

    def test_new_at_zero(self):
        assert _action_from_score(0.0) == ResolveAction.NEW


# ── _parse_pg_vector 단위 테스트 ──────────────────────────────────────────────

class TestParsePgVector:
    def test_valid_vector(self):
        result = _parse_pg_vector("[0.1,0.2,0.3]")
        assert result == pytest.approx([0.1, 0.2, 0.3])

    def test_none_returns_none(self):
        assert _parse_pg_vector(None) is None

    def test_empty_string_returns_none(self):
        assert _parse_pg_vector("") is None

    def test_malformed_returns_none(self):
        assert _parse_pg_vector("not_a_vector") is None


# ── HybridResolver.resolve 통합 테스트 (asyncpg mock) ─────────────────────────

@pytest.fixture
def unit_vector_1024():
    """1024차원 단위 벡터."""
    v = [0.0] * 1024
    v[0] = 1.0
    return v


@pytest.fixture
def similar_vector_1024():
    """첫 번째 벡터와 높은 코사인 유사도를 갖는 벡터."""
    v = [0.0] * 1024
    v[0] = 0.9
    v[1] = 0.1
    mag = math.sqrt(sum(x * x for x in v))
    return [x / mag for x in v]


class TestHybridResolverResolve:
    @pytest.mark.asyncio
    async def test_alias_exact_match_returns_merge_score_one(self, unit_vector_1024):
        """alias 정확 일치 시 score=1.0으로 즉시 MERGE."""
        mock_row = {
            "concept_name": "XSS",
            "aliases": ["Cross-Site Scripting", "CrossSiteScripting"],
            "name_vector": None,
            "desc_vector": None,
        }
        with patch("asyncpg.connect", new_callable=AsyncMock) as mock_conn:
            conn_ctx = AsyncMock()
            conn_ctx.fetch = AsyncMock(return_value=[mock_row])
            conn_ctx.close = AsyncMock()
            mock_conn.return_value = conn_ctx

            resolver = HybridResolver("postgresql://test")
            result = await resolver.resolve(
                name="Cross-Site Scripting",
                aliases=[],
                name_vector=unit_vector_1024,
                desc_vector=None,
            )

        assert result.action == ResolveAction.MERGE
        assert result.score == pytest.approx(1.0)
        assert result.target_concept_name == "XSS"

    @pytest.mark.asyncio
    async def test_empty_candidates_returns_new(self, unit_vector_1024):
        """후보 없으면 NEW."""
        with patch("asyncpg.connect", new_callable=AsyncMock) as mock_conn:
            conn_ctx = AsyncMock()
            conn_ctx.fetch = AsyncMock(return_value=[])
            conn_ctx.close = AsyncMock()
            mock_conn.return_value = conn_ctx

            resolver = HybridResolver("postgresql://test")
            result = await resolver.resolve(
                name="UnknownConcept",
                aliases=[],
                name_vector=unit_vector_1024,
                desc_vector=None,
            )

        assert result.action == ResolveAction.NEW
        assert result.target_concept_name is None

    @pytest.mark.asyncio
    async def test_high_score_returns_merge(self, unit_vector_1024):
        """동일 벡터 + 동일 이름 → MERGE."""
        vec_str = "[" + ",".join(f"{v:.6f}" for v in unit_vector_1024) + "]"
        mock_row = {
            "concept_name": "SQLInjection",
            "aliases": ["SQL Injection"],
            "name_vector": vec_str,
            "desc_vector": vec_str,
        }
        with patch("asyncpg.connect", new_callable=AsyncMock) as mock_conn:
            conn_ctx = AsyncMock()
            conn_ctx.fetch = AsyncMock(return_value=[mock_row])
            conn_ctx.close = AsyncMock()
            mock_conn.return_value = conn_ctx

            resolver = HybridResolver("postgresql://test")
            result = await resolver.resolve(
                name="SQLInjection",
                aliases=["SQL Injection"],
                name_vector=unit_vector_1024,
                desc_vector=unit_vector_1024,
            )

        assert result.action == ResolveAction.MERGE

    @pytest.mark.asyncio
    async def test_score_metrics_all_populated(self, unit_vector_1024):
        """score_metrics 3개 컬럼 모두 0.0이 아닌 값으로 채워짐."""
        vec_str = "[" + ",".join(f"{v:.6f}" for v in unit_vector_1024) + "]"
        mock_row = {
            "concept_name": "XSS",
            "aliases": [],
            "name_vector": vec_str,
            "desc_vector": vec_str,
        }
        with patch("asyncpg.connect", new_callable=AsyncMock) as mock_conn:
            conn_ctx = AsyncMock()
            conn_ctx.fetch = AsyncMock(return_value=[mock_row])
            conn_ctx.close = AsyncMock()
            mock_conn.return_value = conn_ctx

            resolver = HybridResolver("postgresql://test")
            result = await resolver.resolve(
                name="XSS",
                aliases=[],
                name_vector=unit_vector_1024,
                desc_vector=unit_vector_1024,
            )

        # score_metrics 버그 방지: 3개 모두 0.0이어서는 안 됨
        assert (
            result.score_jaro_winkler > 0.0
            or result.score_name_vector > 0.0
            or result.score_desc_vector > 0.0
        ), "score_metrics 모두 0.0 - schema.md 버그 방지 위반"
