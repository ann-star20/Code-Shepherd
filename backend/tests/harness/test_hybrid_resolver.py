"""test_hybrid_resolver.py — 3-Factor 하이브리드 링크 리졸버 TDD 하네스

SDD 스펙 (build_process.md §1):
  Hybrid Score = (JaroWinkler × 0.4) + (CosineName × 0.3) + (CosineDesc × 0.3)

  Score >= 0.88          → MERGE      : 기존 노드에 병합 + Centroid Shifting
  0.72 <= Score < 0.88   → RELATED_TO : [:RELATED_TO] 엣지 연결
  Score < 0.72           → NEW        : 완전 신규 마스터 노드

AAA 패턴:
  Arrange — 픽스처/입력 데이터 준비
  Act     — 테스트 대상 함수 실행
  Assert  — 결과 및 사이드이펙트 검증

테스트 그룹:
  T_hr_U* : 단위 테스트 — 순수 함수, 외부 의존성 없음 (항상 통과)
  T_hr_F* : 가짜 풀 통합 테스트 — FakePgPool/FakeNeo4jDriver로 전체 흐름 검증 (항상 통과)
  T_hr_I* : 실제 DB 통합 테스트 — PostgreSQL + Neo4j 필요, 미실행 시 자동 skip

Mock 데이터 시나리오 매핑 (mock_client.py 창(槍) 3종):
  A — CrossSiteRequestForgery → CSRF 시드에 MERGE + Centroid Shifting (score > 0.88)
  B — SSRF              → CSRF 시드와 RELATED_TO (0.72 <= score < 0.88 — FakePgPool로 강제)
  C — Clickjacking      → 완전 신규 NEW 노드 (score < 0.72)
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from app.domain.models import ConceptExtractionSchema
from app.infrastructure.graph.hybrid_resolver import (
    MERGE_THRESHOLD,
    RELATED_THRESHOLD,
    MergeAction,
    _jaro_winkler,
    _parse_vec,
    compute_hybrid_score,
    hybrid_resolve,
    max_jaro_winkler,
)
from app.infrastructure.llm.mock_embedding import MockEmbeddingService, cosine_sim

# ─────────────────────────────────────────────────────────────────────────────
# 테스트용 인프라 더미 (외부 의존성 없음)
# ─────────────────────────────────────────────────────────────────────────────


class _FakeSession:
    """Neo4j 세션 더미 — 쿼리를 내부 log에 기록만 하고 실제 DB 접근 없음."""

    def __init__(self) -> None:
        self.queries: list[tuple[str, dict]] = []

    async def run(self, query: str, **params: Any) -> None:
        self.queries.append((query, params))

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *_: Any) -> None:
        pass


class _FakeNeo4jDriver:
    """Neo4j AsyncDriver 더미."""

    def __init__(self) -> None:
        self._session = _FakeSession()

    def session(self) -> _FakeSession:
        return self._session

    @property
    def logged_queries(self) -> list[tuple[str, dict]]:
        return self._session.queries


class _FakePgPool:
    """asyncpg.Pool 더미 — 인메모리 개념 목록으로 mock fetch/fetchrow/execute 제공."""

    def __init__(self, concepts: list[dict]) -> None:
        self._concepts: list[dict] = list(concepts)
        self.execute_calls: list[tuple[str, tuple]] = []

    async def fetch(self, query: str, *args: Any) -> list[dict]:
        return list(self._concepts)

    async def fetchrow(self, query: str, *args: Any) -> dict | None:
        target = args[0] if args else None
        return next((c for c in self._concepts if c["concept_name"] == target), None)

    async def execute(self, query: str, *args: Any) -> None:
        self.execute_calls.append((query, args))
        # aliases/domains/name_vector 등 인라인 업데이트 시뮬레이션
        if "UPDATE concepts" in query and len(args) >= 11:
            (
                new_aliases,
                new_domains,
                new_vec_str,
                severity,
                description_ko,
                concept_type,
                cwe_id,
                owasp_id,
                root_cause,
                desc_vec_str,
                name,
            ) = args[:11]
            for c in self._concepts:
                if c["concept_name"] == name:
                    c["aliases"] = list(new_aliases)
                    c["domains"] = list(new_domains)
                    # 문자열 표현을 파싱하여 벡터로 저장
                    c["name_vector"] = _parse_vec(new_vec_str)
                    if severity is not None:
                        c["severity"] = severity
                    if description_ko is not None:
                        c["description_ko"] = description_ko
                    if concept_type is not None:
                        c["concept_type"] = concept_type
                    if cwe_id is not None:
                        c["cwe_id"] = cwe_id
                    if owasp_id is not None:
                        c["owasp_id"] = owasp_id
                    if root_cause is not None:
                        c["root_cause"] = root_cause
                    if desc_vec_str is not None:
                        c["desc_vector"] = _parse_vec(desc_vec_str)
                    break


def _make_concept(
    name: str,
    aliases: list[str] | None = None,
    description_ko: str = "",
    domains: list[str] | None = None,
) -> ConceptExtractionSchema:
    return ConceptExtractionSchema(
        concept_name=name,
        aliases=aliases or [],
        description_ko=description_ko,
        domains=domains or ["security"],
    )


def _seed_record(
    name: str,
    aliases: list[str],
    desc: str,
    emb: MockEmbeddingService,
) -> dict:
    """FakePgPool에 주입할 시드 레코드 — 벡터 사전 계산."""
    name_text = ", ".join([name] + aliases)
    return {
        "concept_name": name,
        "aliases": aliases,
        "domains": ["security"],
        "description_ko": desc,
        "name_vector": emb.embed(name_text),
        "desc_vector": emb.embed(desc),
    }


# ─────────────────────────────────────────────────────────────────────────────
# T_hr_U* : 단위 테스트 — 순수 함수 (DB 불필요)
# ─────────────────────────────────────────────────────────────────────────────


class TestHybridScoreFormula:
    """T_hr_U01~U03 : compute_hybrid_score 산술 검증."""

    def test_U01_perfect_scores_yield_one(self) -> None:
        """Arrange: jw=1.0, name_cos=1.0, desc_cos=1.0
        Act: compute_hybrid_score(1.0, 1.0, 1.0)
        Assert: 결과 == 1.0 (가중치 합 = 0.4+0.3+0.3)
        """
        assert compute_hybrid_score(1.0, 1.0, 1.0) == pytest.approx(1.0)

    def test_U02_merge_boundary_exact(self) -> None:
        """Arrange: 각 인수 = MERGE_THRESHOLD(0.88)
        Act: compute_hybrid_score(0.88, 0.88, 0.88)
        Assert: 결과 == 0.88 → MERGE 분기 진입 임계치 정확
        """
        score = compute_hybrid_score(0.88, 0.88, 0.88)
        assert score == pytest.approx(MERGE_THRESHOLD, abs=1e-9)
        assert score >= MERGE_THRESHOLD

    def test_U03_related_boundary_below_merge(self) -> None:
        """Arrange: 각 인수 = RELATED_THRESHOLD(0.72)
        Act: compute_hybrid_score(0.72, 0.72, 0.72)
        Assert: RELATED_TO 분기 범위 내 (0.72 <= score < 0.88)
        """
        score = compute_hybrid_score(0.72, 0.72, 0.72)
        assert score == pytest.approx(RELATED_THRESHOLD, abs=1e-9)
        assert RELATED_THRESHOLD <= score < MERGE_THRESHOLD

    def test_U04_weights_sum_to_one(self) -> None:
        """가중치 합 = 1.0 (0.4 + 0.3 + 0.3)."""
        from app.infrastructure.graph.hybrid_resolver import (
            WEIGHT_DESC,
            WEIGHT_JW,
            WEIGHT_NAME,
        )

        assert WEIGHT_JW + WEIGHT_NAME + WEIGHT_DESC == pytest.approx(1.0)


class TestJaroWinkler:
    """T_hr_U05~U08 : Jaro-Winkler 정확도 검증."""

    def test_U05_identical_strings_yield_one(self) -> None:
        """Arrange: 동일 문자열 "csrf"
        Act: _jaro_winkler("csrf", "csrf")
        Assert: 1.0
        """
        assert _jaro_winkler("csrf", "csrf") == pytest.approx(1.0)

    def test_U06_exact_alias_match_is_one(self) -> None:
        """Arrange: "cross-site request forgery" 완전 일치 (소문자)
        Act: _jaro_winkler
        Assert: 1.0 — 시나리오 A JW 구성 요소 검증
        """
        s = "cross-site request forgery"
        assert _jaro_winkler(s, s) == pytest.approx(1.0)

    def test_U07_csrf_vs_xsrf_high_similarity(self) -> None:
        """Arrange: "csrf" vs "xsrf" — 3/4 문자 공유
        Act: _jaro_winkler("csrf", "xsrf")
        Assert: >= 0.75 (높은 유사도)
        """
        score = _jaro_winkler("csrf", "xsrf")
        assert score >= 0.75, f"CSRF vs XSRF JW={score:.3f} — 0.75 이상이어야 함"

    def test_U08_empty_string_yields_zero(self) -> None:
        """빈 문자열 입력 → 0.0 (예외 없음)."""
        assert _jaro_winkler("", "csrf") == pytest.approx(0.0)
        assert _jaro_winkler("csrf", "") == pytest.approx(0.0)

    def test_U09_max_jaro_winkler_finds_best_pair(self) -> None:
        """Arrange: pool_a에 완전 일치 항목 포함
        Act: max_jaro_winkler(["CrossSiteRequestForgery", "Cross-Site Request Forgery"], ["CSRF", "Cross-Site Request Forgery"])
        Assert: 1.0 (정확 일치 쌍 발견)
        """
        pool_a = ["CrossSiteRequestForgery", "Cross-Site Request Forgery"]
        pool_b = ["CSRF", "Cross-Site Request Forgery"]
        assert max_jaro_winkler(pool_a, pool_b) == pytest.approx(1.0)

    def test_U10_max_jaro_winkler_empty_pool_returns_zero(self) -> None:
        assert max_jaro_winkler([], ["CSRF"]) == pytest.approx(0.0)
        assert max_jaro_winkler(["CSRF"], []) == pytest.approx(0.0)


class TestMockEmbeddingService:
    """T_hr_U11~U14 : MockEmbeddingService 특성 검증."""

    def test_U11_same_text_yields_same_vector(self) -> None:
        """Arrange: 동일 텍스트 2회 임베딩
        Act: embed(text) × 2
        Assert: 두 벡터 일치 (멱등성)
        """
        emb = MockEmbeddingService()
        text = "CSRF, Cross-Site Request Forgery, XSRF"
        v1 = emb.embed(text)
        v2 = emb.embed(text)
        assert v1 == v2

    def test_U12_l2_normalized(self) -> None:
        """Arrange: 임의 텍스트
        Act: embed(text) → 노름 계산
        Assert: 노름 ≈ 1.0 (L2 정규화 확인)
        """
        import math

        emb = MockEmbeddingService()
        vec = emb.embed("CSRF Cross-Site Request Forgery")
        norm = math.sqrt(sum(x * x for x in vec))
        assert norm == pytest.approx(1.0, abs=1e-6)

    def test_U13_csrf_variants_have_high_cosine(self) -> None:
        """Arrange: CSRF 시드 키워드 풀 vs CrossSiteRequestForgery 유입 풀
        Act: cosine_sim(embed(csrf_pool), embed(variant_pool))
        Assert: > 0.80 — 시나리오 A MERGE 충분 조건 검증
        """
        emb = MockEmbeddingService()
        csrf_pool = (
            "CSRF, Cross-Site Request Forgery, XSRF, Sea Surf, "
            "CrossSiteRequestForgery, CSRFAttack, 크로스 사이트 요청 위조, CSRF Attack"
        )
        variant_pool = "CrossSiteRequestForgery, CSRF, Cross-Site Request Forgery, XSRF, CSRF Attack"
        v1 = emb.embed(csrf_pool)
        v2 = emb.embed(variant_pool)
        sim = cosine_sim(v1, v2)
        assert (
            sim > 0.80
        ), f"CosineName(CSRF시드, CrossSiteRequestForgery) = {sim:.3f} — 0.80 이상이어야 함"

    def test_U14_clickjacking_low_cosine_with_csrf(self) -> None:
        """Arrange: CSRF 풀 vs Clickjacking 풀
        Act: cosine_sim
        Assert: < 0.30 — 공유 토큰 없어 낮은 유사도 (시나리오 C NEW 조건)
        """
        emb = MockEmbeddingService()
        csrf_v = emb.embed(
            "CSRF, Cross-Site Request Forgery, XSRF, 크로스 사이트 요청 위조"
        )
        click_v = emb.embed("Clickjacking, UI Redressing, UIRedressing, 클릭재킹")
        sim = cosine_sim(csrf_v, click_v)
        assert (
            sim < 0.30
        ), f"CosineName(CSRF, Clickjacking) = {sim:.3f} — 0.30 미만이어야 함"


class TestParseVec:
    """_parse_vec 유틸 함수 검증."""

    def test_none_returns_empty(self) -> None:
        assert _parse_vec(None) == []

    def test_list_passthrough(self) -> None:
        v = [0.1, 0.2, 0.3]
        assert _parse_vec(v) == pytest.approx([0.1, 0.2, 0.3])

    def test_string_format(self) -> None:
        s = "[0.10000000,0.20000000,0.30000000]"
        result = _parse_vec(s)
        assert result == pytest.approx([0.1, 0.2, 0.3])


# ─────────────────────────────────────────────────────────────────────────────
# T_hr_F* : 가짜 풀 통합 테스트 — 인메모리 DB로 엔진 전 흐름 검증
# ─────────────────────────────────────────────────────────────────────────────


class TestHybridResolveFakePool:
    """시나리오 A/B/C 전체 흐름을 FakePgPool + FakeNeo4jDriver로 검증."""

    # ── 공용 픽스처 헬퍼 ─────────────────────────────────────────────────────

    # CSRF 시드 설명 — F01~F04 incoming description과 일치시켜 desc_cos=1.0 보장
    _CSRF_SEED_DESC = (
        "크로스 사이트 요청 위조(CSRF)는 인증된 사용자의 브라우저를 통해 "
        "공격자가 원하는 요청을 서버에 강제로 전송하는 공격."
    )

    @staticmethod
    def _csrf_seed(emb: MockEmbeddingService) -> dict:
        """방패(시드) — CSRF 마스터 레코드 (사전 임베딩 포함).

        aliases에 'CSRF Attack'를 포함하지 않음 → F03 precondition 보장.
        """
        aliases = [
            "Cross-Site Request Forgery",
            "XSRF",
            "Sea Surf",
            "CrossSiteRequestForgery",
            "CSRFAttack",
            "CrossSiteRequestForgeryAttack",
            "크로스 사이트 요청 위조",
        ]
        desc = (
            "크로스 사이트 요청 위조(CSRF)는 인증된 사용자의 브라우저를 통해 "
            "공격자가 원하는 요청을 서버에 강제로 전송하는 공격."
        )
        return _seed_record("CSRF", aliases, desc, emb)

    # ── T_hr_F01: 시나리오 A — MERGE ────────────────────────────────────────

    @pytest.mark.anyio
    async def test_F01_scenario_A_merge_into_csrf(self) -> None:
        """시나리오 A: CrossSiteRequestForgery → CSRF MERGE

        Arrange:
          - FakePgPool에 CSRF 시드 레코드 주입 (사전 계산된 bag_embed 벡터)
          - 유입 개념: CrossSiteRequestForgery, aliases에 "Cross-Site Request Forgery" 포함
        Act:
          - hybrid_resolve(CrossSiteRequestForgery, ...)
        Assert:
          - action == MERGE
          - target == "CSRF"
          - score >= 0.88
        """
        emb = MockEmbeddingService()
        seed = self._csrf_seed(emb)
        pg = _FakePgPool([seed])
        neo = _FakeNeo4jDriver()

        incoming = _make_concept(
            "CrossSiteRequestForgery",
            aliases=["CSRF", "Cross-Site Request Forgery", "XSRF", "CSRF Attack"],
            description_ko=self._CSRF_SEED_DESC,
        )

        result = await hybrid_resolve(incoming, pg, neo, emb)

        assert (
            result.action == MergeAction.MERGE
        ), f"action={result.action}, score={result.score:.4f} — MERGE(>=0.88) 기대"
        assert result.target == "CSRF"
        assert result.score >= 0.88, f"score={result.score:.4f} — 0.88 이상이어야 함"

    # ── T_hr_F02: Centroid Shifting 검증 ────────────────────────────────────

    @pytest.mark.anyio
    async def test_F02_centroid_shifting_updates_name_vector(self) -> None:
        """Centroid Shifting: MERGE 후 CSRF의 name_vector가 변경되어야 함

        Arrange:
          - CSRF 시드를 FakePgPool에 주입하고 초기 name_vector 기록
        Act:
          - CrossSiteRequestForgery로 MERGE 실행
        Assert:
          - FakePgPool.execute_calls에 UPDATE 호출 존재
          - 업데이트된 name_vector != 원본 name_vector (중심점 이동 확인)
        """
        emb = MockEmbeddingService()
        seed = self._csrf_seed(emb)
        original_vec = list(seed["name_vector"])
        pg = _FakePgPool([seed])
        neo = _FakeNeo4jDriver()

        incoming = _make_concept(
            "CrossSiteRequestForgery",
            aliases=["CSRF", "Cross-Site Request Forgery", "XSRF", "CSRF Attack"],
            description_ko=self._CSRF_SEED_DESC,
        )

        await hybrid_resolve(incoming, pg, neo, emb)

        # UPDATE 쿼리가 호출되어야 함
        update_calls = [c for c in pg.execute_calls if "UPDATE concepts" in c[0]]
        assert update_calls, "Centroid Shifting — UPDATE concepts 쿼리가 호출되어야 함"

        # 업데이트된 벡터가 원본과 달라야 함
        updated_vec = _parse_vec(update_calls[0][1][2])  # args[2] = new_name_vec_str
        assert (
            updated_vec != original_vec
        ), "name_vector가 원본과 동일 — Centroid Shifting 미발생"

    # ── T_hr_F03: aliases에 신규 동의어 추가 검증 ────────────────────────────

    @pytest.mark.anyio
    async def test_F03_merge_adds_new_alias(self) -> None:
        """MERGE 시 "CSRF Attack" 신규 동의어가 CSRF aliases에 추가되어야 함

        Arrange:
          - CSRF 시드의 aliases에 "CSRF Attack" 없음 (확인)
        Act:
          - CrossSiteRequestForgery (aliases에 "CSRF Attack" 포함) MERGE
        Assert:
          - FakePgPool 내 CSRF 레코드의 aliases에 "CSRF Attack" 포함
        """
        emb = MockEmbeddingService()
        seed = self._csrf_seed(emb)
        assert (
            "CSRF Attack" not in seed["aliases"]
        ), "사전 조건: CSRF 시드에 'CSRF Attack' 없어야 함"
        pg = _FakePgPool([seed])
        neo = _FakeNeo4jDriver()

        incoming = _make_concept(
            "CrossSiteRequestForgery",
            aliases=["CSRF", "Cross-Site Request Forgery", "XSRF", "CSRF Attack"],
            description_ko=self._CSRF_SEED_DESC,
        )
        await hybrid_resolve(incoming, pg, neo, emb)

        updated_aliases: list[str] = pg._concepts[0]["aliases"]
        assert (
            "CSRF Attack" in updated_aliases
        ), f"aliases={updated_aliases} — 'CSRF Attack'가 포함되어야 함"

    # ── T_hr_F04: MERGE 멱등성 — aliases 중복 없음 ───────────────────────────

    @pytest.mark.anyio
    async def test_F04_merge_idempotent_no_duplicate_aliases(self) -> None:
        """같은 MERGE 2회 실행 시 aliases에 중복 항목이 없어야 함

        Arrange: CSRF 시드 + CrossSiteRequestForgery 유입
        Act: hybrid_resolve 2회 실행
        Assert: CSRF aliases에 "CSRF Attack" 정확히 1회만 존재
        """
        emb = MockEmbeddingService()
        seed = self._csrf_seed(emb)
        pg = _FakePgPool([seed])
        neo = _FakeNeo4jDriver()

        incoming = _make_concept(
            "CrossSiteRequestForgery",
            aliases=["CSRF", "Cross-Site Request Forgery", "XSRF", "CSRF Attack"],
            description_ko=self._CSRF_SEED_DESC,
        )

        await hybrid_resolve(incoming, pg, neo, emb)
        await hybrid_resolve(incoming, pg, neo, emb)

        aliases: list[str] = pg._concepts[0]["aliases"]
        count = aliases.count("CSRF Attack")
        assert count == 1, f"'CSRF Attack' 출현 횟수={count} — 중복 없이 1회여야 함"

    # ── T_hr_F05: 시나리오 B — RELATED_TO ───────────────────────────────────

    @pytest.mark.anyio
    async def test_F05_scenario_B_related_to(self) -> None:
        """시나리오 B: SSRF → CSRF에 대해 RELATED_TO 분기 검증

        Arrange (점수 범위 단위 검증):
          - JW(SSRF aliases, CSRF aliases) ≈ 0.83, name_cos=0.60, desc_cos=0.45
          - compute_hybrid_score → [0.72, 0.88) 확인

        Arrange (실제 분기 검증):
          - CSRF 시드에 name_vector = ssrf_name_vec (cosine_name = 1.0)
          - CSRF 시드에 desc_vector = 0.36·ssrf_desc + sqrt(1-0.36²)·e_k (cosine_desc = 0.36)
          - score = JW·0.4 + 1.0·0.3 + 0.36·0.3 ≤ 0.808 < 0.88 → RELATED_TO 보장
        Act:
          - hybrid_resolve(SSRF, FakePgPool[CSRF], ...)
        Assert:
          - action == RELATED_TO, target == "CSRF"
          - Neo4j에 [:RELATED_TO] MERGE 쿼리 전송됨
        """
        emb = MockEmbeddingService()

        # ─ 점수 범위 단위 검증 ───────────────────────────────────────────────
        jw = max_jaro_winkler(
            ["SSRF", "Server-Side Request Forgery"],
            ["CSRF", "Cross-Site Request Forgery", "XSRF"],
        )
        # JW≈0.83, name_cos=0.80, desc_cos=0.65
        # score = 0.4×0.83 + 0.3×0.80 + 0.3×0.65 = 0.332+0.240+0.195 = 0.767 ∈ [0.72, 0.88)
        score_sample = compute_hybrid_score(jw, 0.80, 0.65)
        assert RELATED_THRESHOLD <= score_sample < MERGE_THRESHOLD, (
            f"score={score_sample:.4f} — RELATED_TO 범위 [0.72, 0.88) 기대 "
            f"(JW={jw:.4f}, name_cos=0.80, desc_cos=0.65)"
        )

        # ─ 실제 RELATED_TO 분기 검증 ────────────────────────────────────────
        # CSRF seed: name_vector = ssrf_name_vec  → cosine_name = 1.0
        #            desc_vector = 0.36·ssrf_desc + sqrt(1-0.36²)·e_k → cosine_desc = 0.36
        # 최종 score = JW·0.4 + 1.0·0.3 + 0.36·0.3 ≤ 0.808 → 항상 RELATED_TO
        ssrf_name_text = ", ".join(
            [
                "SSRF",
                "Server-Side Request Forgery",
                "ServerSideRequestForgery",
                "SSRFAttack",
            ]
        )
        ssrf_desc_text = "서버 사이드 요청 위조(SSRF)는 서버가 공격자가 지정한 내부 또는 외부 리소스로 HTTP 요청을 보내도록 유도하는 취약점."
        ssrf_name_vec = emb.embed(ssrf_name_text)
        ssrf_desc_vec = emb.embed(ssrf_desc_text)

        # e_k: ssrf_desc_vec의 영원소 인덱스 방향 단위벡터 (ssrf_desc와 직교)
        k = next(i for i, x in enumerate(ssrf_desc_vec) if abs(x) < 1e-9)
        orth = math.sqrt(1.0 - 0.36**2)
        csrf_desc_vec = [
            0.36 * v + (orth if i == k else 0.0) for i, v in enumerate(ssrf_desc_vec)
        ]

        pg = _FakePgPool(
            [
                {
                    "concept_name": "CSRF",
                    "aliases": ["Cross-Site Request Forgery", "XSRF"],
                    "name_vector": ssrf_name_vec,
                    "desc_vector": csrf_desc_vec,
                }
            ]
        )
        neo = _FakeNeo4jDriver()

        incoming = _make_concept(
            "SSRF",
            aliases=[
                "Server-Side Request Forgery",
                "ServerSideRequestForgery",
                "SSRFAttack",
            ],
            description_ko=ssrf_desc_text,
        )

        result = await hybrid_resolve(incoming, pg, neo, emb)

        assert (
            result.action == MergeAction.RELATED_TO
        ), f"action={result.action}, score={result.score:.4f} — RELATED_TO [0.72, 0.88) 기대"
        assert result.target == "CSRF"
        related_queries = [q for q, _ in neo.logged_queries if "RELATED_TO" in q]
        assert related_queries, "[:RELATED_TO] MERGE 쿼리가 Neo4j에 전송되어야 함"

    # ── T_hr_F06: 시나리오 C — NEW ───────────────────────────────────────────

    @pytest.mark.anyio
    async def test_F06_scenario_C_new_node(self) -> None:
        """시나리오 C: Clickjacking → 완전 신규 NEW 노드

        Arrange:
          - FakePgPool에 CSRF 시드만 존재
          - 유입: Clickjacking (공유 토큰 없음)
        Act:
          - hybrid_resolve(Clickjacking, ...)
        Assert:
          - action == NEW
          - target == None
          - score < RELATED_THRESHOLD (0.72)
        """
        emb = MockEmbeddingService()
        seed = self._csrf_seed(emb)
        pg = _FakePgPool([seed])
        neo = _FakeNeo4jDriver()

        incoming = _make_concept(
            "Clickjacking",
            aliases=["UI Redressing", "UIRedressing", "ClickjackingAttack", "클릭재킹"],
            description_ko=(
                "투명한 iframe을 웹 페이지 위에 덮어씌워 사용자가 "
                "의도치 않은 버튼을 클릭하도록 속이는 UI 교정 공격."
            ),
        )

        result = await hybrid_resolve(incoming, pg, neo, emb)

        assert (
            result.action == MergeAction.NEW
        ), f"action={result.action}, score={result.score:.4f} — NEW(<0.72) 기대"
        assert result.target is None
        assert (
            result.score < RELATED_THRESHOLD
        ), f"score={result.score:.4f} — {RELATED_THRESHOLD} 미만이어야 함"

    # ── T_hr_F07: 빈 DB → NEW ────────────────────────────────────────────────

    @pytest.mark.anyio
    async def test_F07_empty_db_always_new(self) -> None:
        """Arrange: 빈 FakePgPool (기존 개념 없음)
        Act: 어떤 개념이든 hybrid_resolve
        Assert: action == NEW, score == 0.0
        """
        emb = MockEmbeddingService()
        pg = _FakePgPool([])
        neo = _FakeNeo4jDriver()

        result = await hybrid_resolve(_make_concept("AnyConcept"), pg, neo, emb)

        assert result.action == MergeAction.NEW
        assert result.score == pytest.approx(0.0)


# ─────────────────────────────────────────────────────────────────────────────
# T_hr_I* : 실제 DB 통합 테스트 — PostgreSQL + Neo4j 필요 (없으면 자동 skip)
# ─────────────────────────────────────────────────────────────────────────────


def _vec_str(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.8f}" for x in vec) + "]"


@pytest.fixture
async def _csrf_in_pg(asyncpg_pool):
    """PostgreSQL에 CSRF 시드 레코드를 삽입 후 테스트 종료 시 삭제."""
    emb = MockEmbeddingService()
    aliases = [
        "Cross-Site Request Forgery",
        "XSRF",
        "Sea Surf",
        "CrossSiteRequestForgery",
        "CSRFAttack",
        "크로스 사이트 요청 위조",
        "CSRF Attack",
    ]
    desc = (
        "크로스 사이트 요청 위조(CSRF)는 인증된 사용자의 브라우저를 통해 "
        "공격자가 원하는 요청을 서버에 강제로 전송하는 공격."
    )
    name_vec = emb.embed(", ".join(["CSRF"] + aliases))
    desc_vec = emb.embed(desc)

    await asyncpg_pool.execute(
        """
        INSERT INTO concepts
            (concept_name, domains, description_ko, aliases, name_vector, desc_vector)
        VALUES ($1, $2, $3, $4, $5::vector, $6::vector)
        ON CONFLICT (concept_name) DO UPDATE
        SET aliases=$4, name_vector=$5::vector, desc_vector=$6::vector
        """,
        "CSRF",
        ["security"],
        desc,
        aliases,
        _vec_str(name_vec),
        _vec_str(desc_vec),
    )
    yield {"concept_name": "CSRF", "aliases": aliases}
    await asyncpg_pool.execute("DELETE FROM concepts WHERE concept_name = 'CSRF'")


@pytest.mark.anyio
async def test_I01_scenario_A_merge_real_pg(
    asyncpg_pool, async_neo4j_driver, _csrf_in_pg
):
    """T_hr_I01: 실제 PostgreSQL + Neo4j — CrossSiteRequestForgery → CSRF MERGE

    Arrange: _csrf_in_pg 픽스처가 CSRF를 PostgreSQL에 삽입
    Act: hybrid_resolve(CrossSiteRequestForgery, asyncpg_pool, neo4j, emb)
    Assert:
      - action == MERGE, target == "CSRF"
      - PostgreSQL CSRF 레코드의 aliases에 "CSRF Attack" 추가 확인
    """
    emb = MockEmbeddingService()
    incoming = _make_concept(
        "CrossSiteRequestForgery",
        aliases=["CSRF", "Cross-Site Request Forgery", "XSRF", "CSRF Attack"],
        description_ko=(
            "크로스 사이트 요청 위조 — 인증된 사용자의 브라우저 세션 권한을 신뢰하는 점을 악용하여, "
            "공격자가 의도치 않은 상태 변경 요청을 강제로 전송하게 만드는 취약점."
        ),
    )

    result = await hybrid_resolve(incoming, asyncpg_pool, async_neo4j_driver, emb)

    assert (
        result.action == MergeAction.MERGE
    ), f"action={result.action}, score={result.score:.4f}"
    assert result.target == "CSRF"

    # PostgreSQL aliases 업데이트 검증
    row = await asyncpg_pool.fetchrow(
        "SELECT aliases FROM concepts WHERE concept_name = 'CSRF'"
    )
    assert row is not None, "CSRF 레코드가 PostgreSQL에 존재해야 함"
    assert "CSRF Attack" in list(
        row["aliases"]
    ), f"aliases={row['aliases']} — 'CSRF Attack' 추가되어야 함"


@pytest.mark.anyio
async def test_I02_scenario_C_new_real_pg(
    asyncpg_pool, async_neo4j_driver, _csrf_in_pg
):
    """T_hr_I02: 실제 DB — Clickjacking → NEW (CSRF와 무관)

    Arrange: _csrf_in_pg 픽스처 (CSRF만 존재)
    Act: hybrid_resolve(Clickjacking, ...)
    Assert: action == NEW
    """
    emb = MockEmbeddingService()
    incoming = _make_concept(
        "Clickjacking",
        aliases=["UI Redressing", "UIRedressing", "클릭재킹"],
        description_ko="투명한 iframe 오버레이로 사용자를 속이는 UI 교정 공격.",
    )

    result = await hybrid_resolve(incoming, asyncpg_pool, async_neo4j_driver, emb)

    assert (
        result.action == MergeAction.NEW
    ), f"action={result.action}, score={result.score:.4f}"


@pytest.mark.anyio
async def test_I03_centroid_shifting_persisted_real_pg(
    asyncpg_pool, async_neo4j_driver, _csrf_in_pg
):
    """T_hr_I03: 실제 DB — Centroid Shifting 후 name_vector 변경 영속 확인

    Arrange: CSRF의 초기 name_vector를 기록
    Act: CrossSiteRequestForgery MERGE 실행
    Assert: CSRF의 name_vector가 원래 값과 달라야 함
    """
    emb = MockEmbeddingService()

    before_row = await asyncpg_pool.fetchrow(
        "SELECT name_vector::text FROM concepts WHERE concept_name = 'CSRF'"
    )
    before_vec_str = before_row["name_vector"] if before_row else None

    incoming = _make_concept(
        "CrossSiteRequestForgery",
        aliases=["CSRF", "Cross-Site Request Forgery", "XSRF", "CSRF Attack"],
        description_ko="크로스 사이트 요청 위조.",
    )
    result = await hybrid_resolve(incoming, asyncpg_pool, async_neo4j_driver, emb)
    assert result.action == MergeAction.MERGE

    after_row = await asyncpg_pool.fetchrow(
        "SELECT name_vector::text FROM concepts WHERE concept_name = 'CSRF'"
    )
    after_vec_str = after_row["name_vector"] if after_row else None

    assert (
        after_vec_str != before_vec_str
    ), "name_vector가 변경되지 않음 — Centroid Shifting이 PostgreSQL에 영속되어야 함"
