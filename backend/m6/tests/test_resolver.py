"""tests/test_resolver.py — HybridResolver 단위 테스트 (mock 기반, DB 연결 없음)."""

from __future__ import annotations

import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.infrastructure.graph.hybrid_resolver import (
    DESC_VECTOR_THRESHOLD,
    MERGE_THRESHOLD,
    NAME_VECTOR_THRESHOLD,
    RELATED_THRESHOLD,
    HybridResolver,
    ResolveAction,
    _action_from_score,
    _cosine,
    _jaro_winkler_max,
    _normalize_name,
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


def _vec_with_cosine(cos: float) -> list[float]:
    """unit_vector_1024([1,0,...,0])과 코사인 유사도가 정확히 cos인 단위 벡터."""
    v = [0.0] * 1024
    v[0] = cos
    v[1] = math.sqrt(max(0.0, 1.0 - cos * cos))
    return v


# ── _normalize_name 단위 테스트 ───────────────────────────────────────────────

class TestNormalizeName:
    def test_lowercases_and_strips_internal_whitespace(self):
        assert _normalize_name("  Cross Site   Scripting ") == "crosssitescripting"

    def test_already_normalized_unchanged(self):
        assert _normalize_name("xss") == "xss"


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

    @pytest.mark.asyncio
    async def test_stage1_exact_match_with_whitespace_and_case_normalization(self, unit_vector_1024):
        """[1단계] 공백/대소문자만 다른 완전 매칭 → 즉시 MERGE score=1.0."""
        mock_row = {
            "concept_name": "crosssitescripting",
            "aliases": [],
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
                name="  Cross Site   Scripting ",
                aliases=[],
                name_vector=unit_vector_1024,
                desc_vector=None,
            )

        assert result.action == ResolveAction.MERGE
        assert result.score == pytest.approx(1.0)
        assert result.target_concept_name == "crosssitescripting"

    @pytest.mark.asyncio
    async def test_stage2_alias_lookup_match_when_names_differ(self, unit_vector_1024):
        """[2단계] concept_name은 다르지만 incoming name이 기존 alias와 정규화 일치 → MERGE."""
        mock_row = {
            "concept_name": "Cross-Site Scripting",
            "aliases": ["XSS", "CSS Injection"],
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
                name="xss",
                aliases=[],
                name_vector=unit_vector_1024,
                desc_vector=None,
            )

        assert result.action == ResolveAction.MERGE
        assert result.score == pytest.approx(1.0)
        assert result.target_concept_name == "Cross-Site Scripting"

    @pytest.mark.asyncio
    async def test_track_b_merge_when_vectors_high_but_jw_low(self, unit_vector_1024):
        """[트랙 B] 완전 매칭 실패 + name/desc 벡터 유사도 모두 >=0.8 → MERGE 확정."""
        high_cos_vec = _vec_with_cosine(0.85)
        vec_str = "[" + ",".join(f"{v:.6f}" for v in high_cos_vec) + "]"
        mock_row = {
            "concept_name": "Completely Unrelated Term",
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

        assert result.score_jaro_winkler == 0.0
        assert result.score_name_vector >= NAME_VECTOR_THRESHOLD
        assert result.score_desc_vector >= DESC_VECTOR_THRESHOLD
        assert result.action == ResolveAction.MERGE
        assert result.score >= MERGE_THRESHOLD

    @pytest.mark.asyncio
    async def test_related_to_fallback_when_blended_score_meets_threshold(self, unit_vector_1024):
        """트랙 A/B 모두 미충족 + 블렌딩 점수 >= RELATED_THRESHOLD → RELATED_TO."""
        mid_cos_vec = _vec_with_cosine(0.7)
        vec_str = "[" + ",".join(f"{v:.6f}" for v in mid_cos_vec) + "]"
        mock_row = {
            "concept_name": "SQLInjections",
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
                name="SQLInjection",
                aliases=[],
                name_vector=unit_vector_1024,
                desc_vector=unit_vector_1024,
            )

        assert result.score_name_vector < NAME_VECTOR_THRESHOLD
        assert result.score_desc_vector < DESC_VECTOR_THRESHOLD
        assert RELATED_THRESHOLD <= result.score < MERGE_THRESHOLD
        assert result.action == ResolveAction.RELATED_TO

    @pytest.mark.asyncio
    async def test_new_when_below_all_thresholds(self, unit_vector_1024):
        """트랙 A/B 미충족 + 블렌딩 점수 < RELATED_THRESHOLD → NEW."""
        low_cos_vec = _vec_with_cosine(0.3)
        vec_str = "[" + ",".join(f"{v:.6f}" for v in low_cos_vec) + "]"
        mock_row = {
            "concept_name": "Completely Unrelated Term",
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

        assert result.score < RELATED_THRESHOLD
        assert result.action == ResolveAction.NEW


# ── HybridResolver.do_centroid_shift 단위 테스트 (asyncpg mock) ───────────────

class TestDoCentroidShift:
    @pytest.mark.asyncio
    async def test_without_description_updates_name_vector_only(self):
        """new_description_ko 미지정 시 name_vector/aliases만 갱신, desc_vector는 변경 없음."""
        with patch("asyncpg.connect", new_callable=AsyncMock) as mock_connect, \
                patch(
                    "app.infrastructure.graph.hybrid_resolver._embed_async",
                    new_callable=AsyncMock,
                ) as mock_embed:
            conn = AsyncMock()
            conn.__aenter__ = AsyncMock(return_value=conn)
            conn.__aexit__ = AsyncMock(return_value=False)
            conn.transaction = MagicMock(return_value=conn)
            conn.fetchrow = AsyncMock(return_value={"aliases": ["SQL Injection"]})
            conn.execute = AsyncMock()
            conn.close = AsyncMock()
            mock_connect.return_value = conn
            mock_embed.return_value = [0.1] * 1024

            resolver = HybridResolver("postgresql://test")
            await resolver.do_centroid_shift("SQLInjection", ["SQLi"])

        mock_embed.assert_awaited_once()
        conn.execute.assert_awaited_once()
        sql, *params = conn.execute.await_args.args
        assert "desc_vector" not in sql
        assert "description_ko" not in sql

    @pytest.mark.asyncio
    async def test_with_description_reindexes_desc_vector(self):
        """new_description_ko 지정 시 name_vector + desc_vector + description_ko 모두 재인덱싱."""
        with patch("asyncpg.connect", new_callable=AsyncMock) as mock_connect, \
                patch(
                    "app.infrastructure.graph.hybrid_resolver._embed_async",
                    new_callable=AsyncMock,
                ) as mock_embed:
            conn = AsyncMock()
            conn.__aenter__ = AsyncMock(return_value=conn)
            conn.__aexit__ = AsyncMock(return_value=False)
            conn.transaction = MagicMock(return_value=conn)
            conn.fetchrow = AsyncMock(return_value={"aliases": ["SQL Injection"]})
            conn.execute = AsyncMock()
            conn.close = AsyncMock()
            mock_connect.return_value = conn
            mock_embed.side_effect = [[0.1] * 1024, [0.2] * 1024]

            resolver = HybridResolver("postgresql://test")
            await resolver.do_centroid_shift(
                "SQLInjection", ["SQLi"], new_description_ko="갱신된 설명문"
            )

        assert mock_embed.await_count == 2
        conn.execute.assert_awaited_once()
        sql, *params = conn.execute.await_args.args
        assert "desc_vector" in sql
        assert "description_ko" in sql
        assert "갱신된 설명문" in params
