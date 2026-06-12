"""test_score_save.py — 추론 점수 staging_concepts 영속화 TDD 하네스

검증 범주:
  T_ss_U* — compute_resolve_score 순수 계산 (사이드이펙트 없음)
  T_ss_F* — write_with_precomputed 적재 흐름 (재스코어링 없음)
  T_ss_S* — _save_infer_scores staging 업데이트 (mock/production 모드)

mock 환경 조건:
  USE_REAL_LLM=false, USE_REAL_EMBEDDING=false (기본값)
  모든 T_ss_* 테스트는 DB 없이 FakePgPool + FakeNeo4j로 항상 통과한다.
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
    ResolveResult,
    _parse_vec,
    compute_resolve_score,
)
from app.infrastructure.graph.neo4j_service import GraphWriterService
from app.infrastructure.llm.mock_embedding import MockEmbeddingService


# ── 공용 더미 인프라 ──────────────────────────────────────────────────────────


class _FakeSession:
    def __init__(self) -> None:
        self.queries: list[tuple[str, dict]] = []

    async def run(self, query: str, **params: Any) -> None:
        self.queries.append((query, params))

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *_: Any) -> None:
        pass


class _FakeNeo4jDriver:
    def __init__(self) -> None:
        self._session = _FakeSession()

    def session(self) -> _FakeSession:
        return self._session

    @property
    def logged_queries(self) -> list[tuple[str, dict]]:
        return self._session.queries


class _FakeNeo4jConceptRepo:
    """Neo4jConceptRepo 더미 — merge_concept/merge_concept_into 호출 기록."""

    def __init__(self) -> None:
        self.merge_calls: list[str] = []
        self.merge_into_calls: list[tuple[str, str]] = []

    async def merge_concept(self, concept: ConceptExtractionSchema) -> None:
        self.merge_calls.append(concept.concept_name)

    async def merge_concept_into(
        self, concept: ConceptExtractionSchema, master_name: str
    ) -> None:
        self.merge_into_calls.append((concept.concept_name, master_name))


class _FakePgPool:
    """asyncpg.Pool 더미 — concepts 읽기 + 사이드이펙트 추적.

    full_scan_count: is_deprecated 필터 스캔 횟수.
                     compute_resolve_score 재호출 여부 검증에 사용.
    """

    def __init__(self, concepts: list[dict]) -> None:
        self._concepts = list(concepts)
        self.execute_calls: list[tuple[str, tuple]] = []
        self.full_scan_count: int = 0

    async def fetch(self, query: str, *args: Any) -> list[dict]:
        if "is_deprecated" in query:
            self.full_scan_count += 1
        return list(self._concepts)

    async def fetchrow(self, query: str, *args: Any) -> dict | None:
        target = args[0] if args else None
        return next((c for c in self._concepts if c["concept_name"] == target), None)

    async def execute(self, query: str, *args: Any) -> None:
        self.execute_calls.append((query, args))
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


class _FakeStagingPool:
    """staging_concepts UPDATE 전용 Pool 더미.

    _save_infer_scores가 호출하는 UPDATE 쿼리를 인메모리로 시뮬레이션한다.
    """

    def __init__(self) -> None:
        self._staging: list[dict] = []
        self.execute_calls: list[tuple[str, tuple]] = []

    def add_staging(self, session_id: str, concept_name: str) -> None:
        self._staging.append(
            {
                "session_id": str(session_id),
                "concept_json": {"concept_name": concept_name},
                "infer_action": None,
                "infer_score": None,
                "target_concept_name": None,
            }
        )

    async def execute(self, query: str, *args: Any) -> None:
        self.execute_calls.append((query, args))
        if "UPDATE staging_concepts" in query and "infer_action" in query:
            infer_action, infer_score, target_name, session_id, concept_name = args
            for row in self._staging:
                if row["concept_json"]["concept_name"] == concept_name:
                    row["infer_action"] = infer_action
                    row["infer_score"] = infer_score
                    row["target_concept_name"] = target_name

    def get_staging(self, concept_name: str) -> dict | None:
        return next(
            (
                r
                for r in self._staging
                if r["concept_json"]["concept_name"] == concept_name
            ),
            None,
        )


# ── 공용 픽스처 헬퍼 ──────────────────────────────────────────────────────────


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


_CSRF_DESC = (
    "크로스 사이트 요청 위조(CSRF)는 인증된 사용자의 브라우저를 통해 "
    "공격자가 원하는 요청을 서버에 강제로 전송하는 공격."
)


def _csrf_seed(emb: MockEmbeddingService) -> dict:
    aliases = [
        "Cross-Site Request Forgery",
        "XSRF",
        "Sea Surf",
        "CrossSiteRequestForgery",
        "CSRFAttack",
        "CrossSiteRequestForgeryAttack",
        "크로스 사이트 요청 위조",
    ]
    name_text = ", ".join(["CSRF"] + aliases)
    return {
        "concept_name": "CSRF",
        "aliases": aliases,
        "domains": ["security"],
        "description_ko": _CSRF_DESC,
        "name_vector": emb.embed(name_text),
        "desc_vector": emb.embed(_CSRF_DESC),
        "severity": "high",
        "concept_type": "vulnerability_root_cause",
        "cwe_id": "CWE-352",
        "owasp_id": "A01:2021",
        "root_cause": None,
    }


# ── T_ss_U* : compute_resolve_score 단위 테스트 ──────────────────────────────


class TestComputeResolveScore:
    """T_ss_U01~U03 : 순수 점수 계산 — PG/Neo4j 사이드이펙트 없음."""

    @pytest.mark.anyio
    async def test_U01_merge_no_side_effects(self) -> None:
        """compute_resolve_score — MERGE 반환, PG UPDATE 없음.

        Arrange: FakePgPool에 CSRF 시드, 유입 = CrossSiteRequestForgery
        Act: compute_resolve_score(...)
        Assert: action==MERGE, score>=0.88, execute_calls 비어있음
        """
        emb = MockEmbeddingService()
        pg = _FakePgPool([_csrf_seed(emb)])

        incoming = _make_concept(
            "CrossSiteRequestForgery",
            aliases=["CSRF", "Cross-Site Request Forgery", "XSRF"],
            description_ko=_CSRF_DESC,
        )

        result = await compute_resolve_score(incoming, pg, emb)

        assert (
            result.action == MergeAction.MERGE
        ), f"action={result.action}, score={result.score:.4f}"
        assert result.score >= MERGE_THRESHOLD
        assert result.target == "CSRF"
        update_calls = [c for c in pg.execute_calls if "UPDATE" in c[0]]
        assert not update_calls, "compute_resolve_score는 PG를 수정하면 안 됨"

    @pytest.mark.anyio
    async def test_U02_related_to_no_neo4j_needed(self) -> None:
        """compute_resolve_score — RELATED_TO 반환, Neo4j 파라미터 불필요.

        Arrange: SSRF-CSRF RELATED_TO 벡터 시나리오 (test_hybrid_resolver F05 동일)
        Act: compute_resolve_score(SSRF, pg, emb)
        Assert: action==RELATED_TO, RELATED_THRESHOLD <= score < MERGE_THRESHOLD
        """
        emb = MockEmbeddingService()

        ssrf_name_vec = emb.embed(
            ", ".join(
                [
                    "SSRF",
                    "Server-Side Request Forgery",
                    "ServerSideRequestForgery",
                    "SSRFAttack",
                ]
            )
        )
        ssrf_desc_text = (
            "서버 사이드 요청 위조(SSRF)는 서버가 공격자가 지정한 내부 또는 외부 리소스로 "
            "HTTP 요청을 보내도록 유도하는 취약점."
        )
        ssrf_desc_vec = emb.embed(ssrf_desc_text)

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

        incoming = _make_concept(
            "SSRF",
            aliases=[
                "Server-Side Request Forgery",
                "ServerSideRequestForgery",
                "SSRFAttack",
            ],
            description_ko=ssrf_desc_text,
        )

        result = await compute_resolve_score(incoming, pg, emb)

        assert (
            result.action == MergeAction.RELATED_TO
        ), f"action={result.action}, score={result.score:.4f}"
        assert RELATED_THRESHOLD <= result.score < MERGE_THRESHOLD

    @pytest.mark.anyio
    async def test_U03_new_empty_db(self) -> None:
        """compute_resolve_score — 빈 DB → NEW, score=0.0, 스캔 1회.

        Arrange: 빈 FakePgPool
        Act: compute_resolve_score(...)
        Assert: action==NEW, score==0.0, full_scan_count==1 (정확히 1회 스캔)
        """
        emb = MockEmbeddingService()
        pg = _FakePgPool([])

        result = await compute_resolve_score(_make_concept("NewConcept"), pg, emb)

        assert result.action == MergeAction.NEW
        assert result.score == pytest.approx(0.0)
        assert result.target is None
        assert pg.full_scan_count == 1, "스캔 정확히 1회 실행 필수"


# ── T_ss_F* : write_with_precomputed 통합 테스트 ─────────────────────────────


class TestWriteWithPrecomputed:
    """T_ss_F01~F03 : 사전 계산된 ResolveResult로 적재 — hybrid_resolve 재호출 없음."""

    @pytest.mark.anyio
    async def test_F01_merge_centroid_shift_no_rescore(self) -> None:
        """write_with_precomputed(MERGE) — Centroid Shifting 실행, 재스코어링 없음.

        Arrange: CSRF 시드, precomputed = MERGE / "CSRF" / 0.95
        Act: writer.write_with_precomputed(incoming, precomputed)
        Assert:
          - pg_written=False (MERGE → 신규 노드 없음)
          - UPDATE concepts 쿼리 1건 이상 (Centroid Shifting)
          - full_scan_count==0 (재스코어링 없음)
        """
        emb = MockEmbeddingService()
        seed = _csrf_seed(emb)
        pg = _FakePgPool([seed])
        neo = _FakeNeo4jDriver()
        repo = _FakeNeo4jConceptRepo()

        incoming = _make_concept(
            "CrossSiteRequestForgery",
            aliases=["CSRF", "Cross-Site Request Forgery"],
        )
        precomputed = ResolveResult(
            MergeAction.MERGE, "CSRF", 0.95, "CrossSiteRequestForgery"
        )

        writer = GraphWriterService(pg, neo, repo, emb)
        result = await writer.write_with_precomputed(incoming, precomputed)

        assert result.pg_written is False
        assert result.resolve.action == MergeAction.MERGE
        assert result.resolve.score == pytest.approx(0.95)

        update_calls = [c for c in pg.execute_calls if "UPDATE concepts" in c[0]]
        assert update_calls, "MERGE → Centroid Shifting(UPDATE concepts) 필수"
        assert pg.full_scan_count == 0, "write_with_precomputed → 재스코어링 금지"

    @pytest.mark.anyio
    async def test_F01b_merge_propagates_enrichment_to_target(self) -> None:
        """write_with_precomputed(MERGE) — incoming concept의 enrichment가 target row에 전파.

        Arrange: CSRF 시드(domains=["security"], cwe_id="CWE-352", owasp_id="A01:2021",
                 root_cause=None, description_ko=_CSRF_DESC),
                 incoming = domains=["performance"] 추가 + cwe_id 미제공(None) +
                 owasp_id 신규값 + root_cause 신규값 + description_ko 미제공("")
        Act: writer.write_with_precomputed(incoming, MERGE → "CSRF")
        Assert:
          - domains: 기존 + 신규 합집합 (apoc.coll.toSet과 동일한 Append+Dedupe 정책)
          - cwe_id: incoming이 None이므로 COALESCE로 기존 값 유지 (CWE-352)
          - owasp_id: incoming이 non-null이므로 덮어쓰기 (Overwrite-if-not-null)
          - root_cause: 기존이 None이므로 incoming 값으로 채워짐
          - description_ko: incoming이 빈 문자열("")이므로 NULL 취급 → 기존 값 유지,
            desc_vector 재임베딩 없음
        """
        emb = MockEmbeddingService()
        seed = _csrf_seed(emb)
        pg = _FakePgPool([seed])
        neo = _FakeNeo4jDriver()
        repo = _FakeNeo4jConceptRepo()

        incoming = ConceptExtractionSchema(
            concept_name="CrossSiteRequestForgery",
            aliases=["CSRF"],
            domains=["performance"],
            cwe_id=None,
            owasp_id="A99:2099",
            root_cause="잘못된 토큰 검증",
            description_ko="",
        )
        precomputed = ResolveResult(
            MergeAction.MERGE, "CSRF", 0.95, "CrossSiteRequestForgery"
        )

        writer = GraphWriterService(pg, neo, repo, emb)
        await writer.write_with_precomputed(incoming, precomputed)

        updated = next(c for c in pg._concepts if c["concept_name"] == "CSRF")
        assert set(updated["domains"]) == {
            "security",
            "performance",
        }, "domains: append+dedupe (apoc.coll.toSet과 동일 정책)"
        assert (
            updated["cwe_id"] == "CWE-352"
        ), "cwe_id: incoming이 None이면 COALESCE로 기존 유지"
        assert (
            updated["owasp_id"] == "A99:2099"
        ), "owasp_id: incoming이 non-null이면 덮어쓰기"
        assert (
            updated["root_cause"] == "잘못된 토큰 검증"
        ), "root_cause: 기존 None → incoming 값 반영"
        assert (
            updated["description_ko"] == _CSRF_DESC
        ), "description_ko: incoming이 빈 문자열이면 NULL 취급되어 기존 값 유지"
        assert repo.merge_into_calls == [
            ("CrossSiteRequestForgery", "CSRF")
        ], "MERGE(pre): repo.merge_concept_into(concept, target)으로 4-레이어 전체 적재"

    @pytest.mark.anyio
    async def test_F02_related_to_creates_edge_no_rescore(self) -> None:
        """write_with_precomputed(RELATED_TO) — 신규 노드 + [:RELATED_TO] 엣지, 재스코어링 없음.

        Arrange: precomputed = RELATED_TO / "CSRF" / 0.78
        Act: writer.write_with_precomputed(SSRF, precomputed)
        Assert:
          - pg_written=True
          - Neo4j에 RELATED_TO 키워드 포함 쿼리 존재
          - full_scan_count==0
        """
        emb = MockEmbeddingService()
        pg = _FakePgPool([])
        neo = _FakeNeo4jDriver()
        repo = _FakeNeo4jConceptRepo()

        incoming = _make_concept("SSRF", aliases=["Server-Side Request Forgery"])
        precomputed = ResolveResult(MergeAction.RELATED_TO, "CSRF", 0.78, "SSRF")

        writer = GraphWriterService(pg, neo, repo, emb)
        result = await writer.write_with_precomputed(incoming, precomputed)

        assert result.pg_written is True
        related_queries = [q for q, _ in neo.logged_queries if "RELATED_TO" in q]
        assert related_queries, "RELATED_TO 분기 → [:RELATED_TO] Neo4j 쿼리 필수"
        assert pg.full_scan_count == 0

    @pytest.mark.anyio
    async def test_F03_new_no_edge_no_rescore(self) -> None:
        """write_with_precomputed(NEW) — 신규 노드만, RELATED_TO 엣지 없음.

        Arrange: precomputed = NEW / None / 0.30
        Act: writer.write_with_precomputed(Clickjacking, precomputed)
        Assert:
          - pg_written=True
          - Neo4j에 RELATED_TO 쿼리 없음
          - full_scan_count==0
        """
        emb = MockEmbeddingService()
        pg = _FakePgPool([])
        neo = _FakeNeo4jDriver()
        repo = _FakeNeo4jConceptRepo()

        incoming = _make_concept("Clickjacking", aliases=["UI Redressing"])
        precomputed = ResolveResult(MergeAction.NEW, None, 0.30, "Clickjacking")

        writer = GraphWriterService(pg, neo, repo, emb)
        result = await writer.write_with_precomputed(incoming, precomputed)

        assert result.pg_written is True
        related_queries = [q for q, _ in neo.logged_queries if "RELATED_TO" in q]
        assert not related_queries, "NEW 분기 → RELATED_TO 엣지 없어야 함"
        assert pg.full_scan_count == 0


# ── T_ss_S* : _save_infer_scores staging 업데이트 ────────────────────────────


class TestSaveInferScores:
    """T_ss_S01~S02 : staging_concepts 3컬럼 업데이트 검증."""

    @pytest.mark.anyio
    async def test_S01_all_three_columns_saved(self) -> None:
        """_save_infer_scores — infer_action/infer_score/target_concept_name 모두 저장.

        Arrange: FakeStagingPool에 2개 레코드 (MERGE용, NEW용)
        Act: _save_infer_scores([MERGE, NEW])
        Assert: 각 레코드에 올바른 3컬럼 값이 반영됨
        """
        from app.worker.tasks import _save_infer_scores

        pool = _FakeStagingPool()
        session_id = "aabbccdd-0000-0000-0000-000000000001"

        pool.add_staging(session_id, "CrossSiteRequestForgery")
        pool.add_staging(session_id, "Clickjacking")

        concepts = [
            _make_concept("CrossSiteRequestForgery"),
            _make_concept("Clickjacking"),
        ]
        results = [
            ResolveResult(MergeAction.MERGE, "CSRF", 0.95, "CrossSiteRequestForgery"),
            ResolveResult(MergeAction.NEW, None, 0.30, "Clickjacking"),
        ]

        await _save_infer_scores(session_id, concepts, results, pool)

        csrf_row = pool.get_staging("CrossSiteRequestForgery")
        assert csrf_row is not None
        assert csrf_row["infer_action"] == "MERGE"
        assert csrf_row["infer_score"] == pytest.approx(0.95)
        assert csrf_row["target_concept_name"] == "CSRF"

        click_row = pool.get_staging("Clickjacking")
        assert click_row is not None
        assert click_row["infer_action"] == "NEW"
        assert click_row["infer_score"] == pytest.approx(0.30)
        assert click_row["target_concept_name"] is None

    @pytest.mark.anyio
    async def test_S02_mock_and_production_mode_identical(self) -> None:
        """_save_infer_scores — mock/production 환경 플래그 무관하게 동일 결과.

        Arrange: "mock" / "production" 레이블로 각각 FakeStagingPool 생성
        Act: _save_infer_scores(RELATED_TO) × 2
        Assert: 두 케이스 모두 infer_action=RELATED_TO, target=ExistingNode
        """
        from app.worker.tasks import _save_infer_scores

        for mode in ("mock", "production"):
            pool = _FakeStagingPool()
            session_id = f"session-{mode[:4]}-0000-0000-000000000001"
            pool.add_staging(session_id, "TestConcept")

            concepts = [_make_concept("TestConcept")]
            results = [
                ResolveResult(
                    MergeAction.RELATED_TO, "ExistingNode", 0.81, "TestConcept"
                )
            ]

            await _save_infer_scores(session_id, concepts, results, pool)

            row = pool.get_staging("TestConcept")
            assert row is not None
            assert row["infer_action"] == "RELATED_TO", f"[{mode}] infer_action 오류"
            assert row["infer_score"] == pytest.approx(
                0.81
            ), f"[{mode}] infer_score 오류"
            assert row["target_concept_name"] == "ExistingNode", f"[{mode}] target 오류"
