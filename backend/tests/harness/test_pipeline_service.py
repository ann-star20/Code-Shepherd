"""test_pipeline_service.py — GraphWriterService + run_link_resolve TDD 하네스

SDD 스펙 (pipeline_service.md):

  GraphWriterService.write():
    MERGE      (score >= 0.88): hybrid_resolve._do_merge 이미 완료 → 추가 PG/Neo4j 쓰기 없음
    RELATED_TO (0.72 <= score < 0.88): PG upsert + Neo4j 4-레이어 MERGE → pg_written=True
    NEW        (score < 0.72): 동일하게 PG upsert + Neo4j 4-레이어 MERGE → pg_written=True

  GraphWriterService._upsert_pg():
    severity='info' → 'low' 정규화, severity=None → 'medium' 기본값
    ON CONFLICT(concept_name): domains/aliases 배열 합집합, root_cause COALESCE

  run_link_resolve():
    MERGE      → staging_concepts.state = COMMITTED (자동 흡수)
    RELATED_TO → staging_concepts.state = APPROVED  (HITL 최종 커밋 대기)
    NEW        → staging_concepts.state = DRAFT 유지 (HITL 검토 대상, state 변경 없음)
    개별 write() 실패 → skip + continue (나머지 개념 처리 지속)

AAA 패턴:
  Arrange — FakePool / FakeRepo / mock WriteResult 준비
  Act     — write() / run_link_resolve() 실행
  Assert  — WriteResult 필드 / execute_calls / staging state 검증

테스트 그룹:
  T_gws_U* : GraphWriterService.write() 단위 테스트 (hybrid_resolve AsyncMock 패치)
  T_gws_F* : _upsert_pg SQL 파라미터 검증 (NEW/RELATED_TO 분기 실제 실행)
  T_gws_R* : run_link_resolve 단위 테스트 (FakeStagingPgPool + FakeGraphWriterService)
"""
from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.domain.models import ConceptExtractionSchema
from app.infrastructure.graph.hybrid_resolver import MergeAction, ResolveResult
from app.infrastructure.graph.neo4j_service import GraphWriterService, WriteResult
from app.infrastructure.llm.mock_embedding import MockEmbeddingService
from app.usecases.run_pipeline import run_link_resolve


# ─────────────────────────────────────────────────────────────────────────────
# 테스트 인프라 더미
# ─────────────────────────────────────────────────────────────────────────────

class _FakeMinimalPgPool:
    """GraphWriterService._upsert_pg 전용 더미 — execute 호출만 추적."""

    def __init__(self) -> None:
        self.execute_calls: list[tuple[str, tuple]] = []

    async def execute(self, query: str, *args: Any) -> None:
        self.execute_calls.append((query, args))

    async def fetch(self, query: str, *args: Any) -> list[dict]:
        return []

    async def fetchrow(self, query: str, *args: Any) -> dict | None:
        return None


class _FakeNeo4jRepo:
    """Neo4jConceptRepo 더미 — merge_concept 호출 기록."""

    def __init__(self) -> None:
        self.merge_calls: list[str] = []

    async def merge_concept(self, concept: ConceptExtractionSchema) -> str:
        self.merge_calls.append(concept.concept_name)
        return concept.concept_name

    async def find_master_by_alias(self, alias: str) -> str | None:
        return None


class _FakeNeo4jDriver:
    """Neo4j AsyncDriver 더미 — 쿼리 없이 세션 컨텍스트 제공."""

    def session(self) -> "_FakeSession":
        return _FakeSession()


class _FakeSession:
    def __init__(self) -> None:
        self.queries: list[tuple[str, dict]] = []

    async def run(self, query: str, **params: Any) -> None:
        self.queries.append((query, params))

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *_: Any) -> None:
        pass


class _FakeStagingPgPool:
    """run_link_resolve 전용 — staging_concepts 인메모리 + state 전이 시뮬레이션."""

    def __init__(self, staging_rows: list[dict]) -> None:
        self._staging = list(staging_rows)
        self.execute_calls: list[tuple[str, tuple]] = []

    async def fetch(self, query: str, *args: Any) -> list[dict]:
        return [r for r in self._staging if r.get("state") == "DRAFT"]

    async def fetchrow(self, query: str, *args: Any) -> dict | None:
        return None

    async def execute(self, query: str, *args: Any) -> None:
        self.execute_calls.append((query, args))
        row_id = args[0] if args else None
        if "COMMITTED" in query:
            for r in self._staging:
                if r["id"] == row_id:
                    r["state"] = "COMMITTED"
        elif "APPROVED" in query:
            for r in self._staging:
                if r["id"] == row_id:
                    r["state"] = "APPROVED"

    def state_of(self, row_id: str) -> str:
        for r in self._staging:
            if r["id"] == row_id:
                return str(r.get("state", "UNKNOWN"))
        return "UNKNOWN"


class _FakeGraphWriterService:
    """GraphWriterService 더미 — run_link_resolve 분기 테스트용 미리 설정된 WriteResult 반환."""

    def __init__(self, results: dict[str, WriteResult]) -> None:
        self._results = results
        self.write_calls: list[str] = []

    async def write(self, concept: ConceptExtractionSchema) -> WriteResult:
        self.write_calls.append(concept.concept_name)
        if concept.concept_name not in self._results:
            raise ValueError(f"사전 설정 없음: {concept.concept_name}")
        return self._results[concept.concept_name]


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


def _staging_row(concept: ConceptExtractionSchema) -> dict:
    """DRAFT 상태의 staging_concepts 인메모리 레코드 생성."""
    return {
        "id": str(uuid.uuid4()),
        "concept_json": json.dumps(concept.model_dump()),
        "state": "DRAFT",
    }


def _write_result(action: MergeAction, target: str | None = None, score: float = 0.9) -> WriteResult:
    return WriteResult(
        resolve=ResolveResult(action, target, score, "IncomingConcept"),
        pg_written=(action != MergeAction.MERGE),
    )


# ─────────────────────────────────────────────────────────────────────────────
# T_gws_U* : GraphWriterService.write() 단위 테스트 (hybrid_resolve AsyncMock)
# ─────────────────────────────────────────────────────────────────────────────

class TestGraphWriterServiceWrite:
    """T_gws_U01~U03: write() 액션별 분기 — PG/Neo4j 쓰기 제어 검증."""

    @pytest.mark.anyio
    async def test_U01_merge_no_pg_write(self) -> None:
        """Arrange: hybrid_resolve → MERGE(score=0.95)
        Act: writer.write(CrossSiteRequestForgery)
        Assert:
          - pg_written == False
          - PG execute_calls 비어 있음 (upsert 미호출)
          - repo.merge_calls 비어 있음
        """
        pg = _FakeMinimalPgPool()
        repo = _FakeNeo4jRepo()
        writer = GraphWriterService(pg, _FakeNeo4jDriver(), repo, MockEmbeddingService())
        concept = _make_concept("CrossSiteRequestForgery", aliases=["CSRF"])
        mock_resolve = ResolveResult(MergeAction.MERGE, "CSRF", 0.95, "CrossSiteRequestForgery")

        with patch(
            "app.infrastructure.graph.neo4j_service.hybrid_resolve",
            new=AsyncMock(return_value=mock_resolve),
        ):
            result = await writer.write(concept)

        assert result.pg_written is False, "MERGE: pg_written=False (추가 쓰기 없음)"
        assert result.resolve.action == MergeAction.MERGE
        assert result.resolve.target == "CSRF"
        assert pg.execute_calls == [], "MERGE: _upsert_pg 미호출 → execute_calls 비어 있음"
        assert repo.merge_calls == [], "MERGE: repo.merge_concept 미호출"

    @pytest.mark.anyio
    async def test_U02_related_to_writes_pg_and_neo4j(self) -> None:
        """Arrange: hybrid_resolve → RELATED_TO(score=0.80)
        Act: writer.write(SSRF)
        Assert:
          - pg_written == True
          - PG execute_calls 1건 (upsert INSERT)
          - repo.merge_calls == ["SSRF"]
        """
        pg = _FakeMinimalPgPool()
        repo = _FakeNeo4jRepo()
        writer = GraphWriterService(pg, _FakeNeo4jDriver(), repo, MockEmbeddingService())
        concept = _make_concept("SSRF", aliases=["Server-Side Request Forgery"])
        mock_resolve = ResolveResult(MergeAction.RELATED_TO, "CSRF", 0.80, "SSRF")

        with patch(
            "app.infrastructure.graph.neo4j_service.hybrid_resolve",
            new=AsyncMock(return_value=mock_resolve),
        ):
            result = await writer.write(concept)

        assert result.pg_written is True, "RELATED_TO: pg_written=True"
        assert result.resolve.action == MergeAction.RELATED_TO
        assert len(pg.execute_calls) == 1, "RELATED_TO: _upsert_pg execute 1회 호출"
        assert repo.merge_calls == ["SSRF"], "RELATED_TO: repo.merge_concept('SSRF') 호출"

    @pytest.mark.anyio
    async def test_U03_new_writes_pg_and_neo4j(self) -> None:
        """Arrange: hybrid_resolve → NEW(score=0.40)
        Act: writer.write(Clickjacking)
        Assert:
          - pg_written == True
          - PG execute_calls 1건
          - repo.merge_calls == ["Clickjacking"]
        """
        pg = _FakeMinimalPgPool()
        repo = _FakeNeo4jRepo()
        writer = GraphWriterService(pg, _FakeNeo4jDriver(), repo, MockEmbeddingService())
        concept = _make_concept("Clickjacking", aliases=["UI Redressing"])
        mock_resolve = ResolveResult(MergeAction.NEW, None, 0.40, "Clickjacking")

        with patch(
            "app.infrastructure.graph.neo4j_service.hybrid_resolve",
            new=AsyncMock(return_value=mock_resolve),
        ):
            result = await writer.write(concept)

        assert result.pg_written is True, "NEW: pg_written=True"
        assert result.resolve.action == MergeAction.NEW
        assert result.resolve.target is None
        assert len(pg.execute_calls) == 1, "NEW: _upsert_pg execute 1회 호출"
        assert repo.merge_calls == ["Clickjacking"], "NEW: repo.merge_concept('Clickjacking') 호출"

    @pytest.mark.anyio
    async def test_U04_write_result_carries_resolve_result(self) -> None:
        """Arrange: MERGE resolve result with specific score/target
        Act: writer.write()
        Assert: result.resolve 필드가 hybrid_resolve 반환값과 동일
        """
        pg = _FakeMinimalPgPool()
        writer = GraphWriterService(pg, _FakeNeo4jDriver(), _FakeNeo4jRepo(), MockEmbeddingService())
        concept = _make_concept("TestConcept")
        mock_resolve = ResolveResult(MergeAction.MERGE, "ExistingMaster", 0.92, "TestConcept")

        with patch(
            "app.infrastructure.graph.neo4j_service.hybrid_resolve",
            new=AsyncMock(return_value=mock_resolve),
        ):
            result = await writer.write(concept)

        assert result.resolve is mock_resolve, "WriteResult.resolve == hybrid_resolve 반환값"
        assert result.resolve.score == pytest.approx(0.92)
        assert result.resolve.target == "ExistingMaster"


# ─────────────────────────────────────────────────────────────────────────────
# T_gws_F* : _upsert_pg SQL 파라미터 검증 (NEW 분기 실행)
# ─────────────────────────────────────────────────────────────────────────────

class TestGraphWriterServiceUpsertPg:
    """T_gws_F01~F04: _upsert_pg 파라미터 규칙 검증."""

    @pytest.mark.anyio
    async def test_F01_correct_concept_name_passed(self) -> None:
        """Arrange: NEW 분기 concept_name='SSRF'
        Act: writer.write(SSRF)
        Assert: execute args[0] == 'SSRF'
        """
        pg = _FakeMinimalPgPool()
        writer = GraphWriterService(pg, _FakeNeo4jDriver(), _FakeNeo4jRepo(), MockEmbeddingService())
        concept = _make_concept("SSRF", aliases=["Server-Side Request Forgery"])

        with patch(
            "app.infrastructure.graph.neo4j_service.hybrid_resolve",
            new=AsyncMock(return_value=ResolveResult(MergeAction.NEW, None, 0.40, "SSRF")),
        ):
            await writer.write(concept)

        _, args = pg.execute_calls[0]
        assert args[0] == "SSRF"

    @pytest.mark.anyio
    async def test_F02_info_severity_normalized_to_low(self) -> None:
        """Arrange: severity='info' 개념
        Act: NEW 분기 write()
        Assert: execute args[3] == 'low' (info → low 정규화)
        """
        pg = _FakeMinimalPgPool()
        writer = GraphWriterService(pg, _FakeNeo4jDriver(), _FakeNeo4jRepo(), MockEmbeddingService())
        concept = ConceptExtractionSchema(
            concept_name="InfoLevelConcept",
            domains=["security"],
            severity="info",
        )

        with patch(
            "app.infrastructure.graph.neo4j_service.hybrid_resolve",
            new=AsyncMock(return_value=ResolveResult(MergeAction.NEW, None, 0.30, "InfoLevelConcept")),
        ):
            await writer.write(concept)

        _, args = pg.execute_calls[0]
        assert args[3] == "low", f"severity 'info' → 'low' 정규화 실패: {args[3]!r}"

    @pytest.mark.anyio
    async def test_F03_none_severity_defaults_to_medium(self) -> None:
        """Arrange: severity=None 개념
        Act: NEW 분기 write()
        Assert: execute args[3] == 'medium' (None → medium 기본값)
        """
        pg = _FakeMinimalPgPool()
        writer = GraphWriterService(pg, _FakeNeo4jDriver(), _FakeNeo4jRepo(), MockEmbeddingService())
        concept = ConceptExtractionSchema(
            concept_name="NoSeverityConcept",
            domains=["performance"],
            severity=None,
        )

        with patch(
            "app.infrastructure.graph.neo4j_service.hybrid_resolve",
            new=AsyncMock(return_value=ResolveResult(MergeAction.NEW, None, 0.20, "NoSeverityConcept")),
        ):
            await writer.write(concept)

        _, args = pg.execute_calls[0]
        assert args[3] == "medium", f"severity=None → 'medium' 기본값 실패: {args[3]!r}"

    @pytest.mark.anyio
    async def test_F04_domains_and_aliases_passed_correctly(self) -> None:
        """Arrange: domains=['security','performance'], aliases=['SsrfVulnerability','SSRFAttack']
        Act: NEW 분기 write()
        Assert: execute args[2] == domains, args[8] == aliases
        """
        pg = _FakeMinimalPgPool()
        writer = GraphWriterService(pg, _FakeNeo4jDriver(), _FakeNeo4jRepo(), MockEmbeddingService())
        concept = _make_concept(
            "SSRF",
            aliases=["SsrfVulnerability", "SSRFAttack"],
            domains=["security", "performance"],
        )

        with patch(
            "app.infrastructure.graph.neo4j_service.hybrid_resolve",
            new=AsyncMock(return_value=ResolveResult(MergeAction.NEW, None, 0.40, "SSRF")),
        ):
            await writer.write(concept)

        _, args = pg.execute_calls[0]
        assert set(args[2]) == {"security", "performance"}, f"domains 불일치: {args[2]}"
        assert set(args[8]) == {"SsrfVulnerability", "SSRFAttack"}, f"aliases 불일치: {args[8]}"

    @pytest.mark.anyio
    async def test_F05_upsert_contains_on_conflict_clause(self) -> None:
        """Arrange: NEW 분기 write()
        Act: execute 호출
        Assert: SQL에 ON CONFLICT (concept_name) DO UPDATE 포함 (멱등성 보장)
        """
        pg = _FakeMinimalPgPool()
        writer = GraphWriterService(pg, _FakeNeo4jDriver(), _FakeNeo4jRepo(), MockEmbeddingService())
        concept = _make_concept("IdempotentConcept")

        with patch(
            "app.infrastructure.graph.neo4j_service.hybrid_resolve",
            new=AsyncMock(return_value=ResolveResult(MergeAction.NEW, None, 0.20, "IdempotentConcept")),
        ):
            await writer.write(concept)

        query, _ = pg.execute_calls[0]
        assert "ON CONFLICT" in query, "upsert 쿼리에 ON CONFLICT 절 누락"
        assert "DO UPDATE" in query, "upsert 쿼리에 DO UPDATE 절 누락"


# ─────────────────────────────────────────────────────────────────────────────
# T_gws_R* : run_link_resolve 단위 테스트
# ─────────────────────────────────────────────────────────────────────────────

class TestRunLinkResolve:
    """T_gws_R01~R06: staging state 전이 + 집계 + 예외 처리 검증."""

    @pytest.mark.anyio
    async def test_R01_empty_staging_returns_zero_summary(self) -> None:
        """Arrange: DRAFT 스테이징 행 없음
        Act: run_link_resolve
        Assert: {"MERGE":0, "RELATED_TO":0, "NEW":0}, write 미호출
        """
        pg = _FakeStagingPgPool([])
        writer = _FakeGraphWriterService({})

        result = await run_link_resolve("sess-empty", pg, writer)

        assert result == {"MERGE": 0, "RELATED_TO": 0, "NEW": 0}
        assert writer.write_calls == [], "DRAFT 행 없음 → write 미호출"

    @pytest.mark.anyio
    async def test_R02_merge_action_transitions_state_to_committed(self) -> None:
        """Arrange: DRAFT staging, writer → MERGE 반환
        Act: run_link_resolve
        Assert:
          - staging state = COMMITTED
          - summary["MERGE"] == 1
          - COMMITTED UPDATE 쿼리 1회 호출
        """
        concept = _make_concept("CrossSiteRequestForgery", aliases=["CSRF"])
        row = _staging_row(concept)
        pg = _FakeStagingPgPool([row])
        writer = _FakeGraphWriterService({
            "CrossSiteRequestForgery": WriteResult(
                resolve=ResolveResult(MergeAction.MERGE, "CSRF", 0.95, "CrossSiteRequestForgery"),
                pg_written=False,
            )
        })

        summary = await run_link_resolve("sess-merge", pg, writer)

        assert summary["MERGE"] == 1
        assert summary["RELATED_TO"] == 0
        assert summary["NEW"] == 0
        assert pg.state_of(row["id"]) == "COMMITTED", "MERGE → staging state COMMITTED"
        committed_calls = [c for c in pg.execute_calls if "COMMITTED" in c[0]]
        assert len(committed_calls) == 1, "COMMITTED UPDATE 쿼리 1회"

    @pytest.mark.anyio
    async def test_R03_related_to_action_transitions_state_to_approved(self) -> None:
        """Arrange: DRAFT staging, writer → RELATED_TO 반환
        Act: run_link_resolve
        Assert:
          - staging state = APPROVED
          - summary["RELATED_TO"] == 1
        """
        concept = _make_concept("SSRF", aliases=["Server-Side Request Forgery"])
        row = _staging_row(concept)
        pg = _FakeStagingPgPool([row])
        writer = _FakeGraphWriterService({
            "SSRF": WriteResult(
                resolve=ResolveResult(MergeAction.RELATED_TO, "CSRF", 0.80, "SSRF"),
                pg_written=True,
            )
        })

        summary = await run_link_resolve("sess-related", pg, writer)

        assert summary["RELATED_TO"] == 1
        assert pg.state_of(row["id"]) == "APPROVED", "RELATED_TO → staging state APPROVED"
        approved_calls = [c for c in pg.execute_calls if "APPROVED" in c[0]]
        assert len(approved_calls) == 1

    @pytest.mark.anyio
    async def test_R04_new_action_keeps_state_draft(self) -> None:
        """Arrange: DRAFT staging, writer → NEW 반환
        Act: run_link_resolve
        Assert:
          - staging state = DRAFT (변경 없음)
          - summary["NEW"] == 1
          - execute_calls 비어 있음 (state 변경 없음)
        """
        concept = _make_concept("Clickjacking", aliases=["UI Redressing"])
        row = _staging_row(concept)
        pg = _FakeStagingPgPool([row])
        writer = _FakeGraphWriterService({
            "Clickjacking": WriteResult(
                resolve=ResolveResult(MergeAction.NEW, None, 0.40, "Clickjacking"),
                pg_written=True,
            )
        })

        summary = await run_link_resolve("sess-new", pg, writer)

        assert summary["NEW"] == 1
        assert pg.state_of(row["id"]) == "DRAFT", "NEW → staging state DRAFT 유지"
        assert pg.execute_calls == [], "NEW: staging UPDATE 없음"

    @pytest.mark.anyio
    async def test_R05_write_exception_skips_and_continues(self) -> None:
        """Arrange: 3개 DRAFT 행, 2번째 write() → RuntimeError
        Act: run_link_resolve
        Assert:
          - 예외 전파 없음 (함수 정상 반환)
          - summary["NEW"] == 2 (실패 1개 제외)
          - write_calls에 3개 모두 시도됨
        """
        c1 = _make_concept("ConceptA")
        c2 = _make_concept("ConceptB")
        c3 = _make_concept("ConceptC")
        rows = [_staging_row(c1), _staging_row(c2), _staging_row(c3)]
        pg = _FakeStagingPgPool(rows)

        ok_result = WriteResult(
            resolve=ResolveResult(MergeAction.NEW, None, 0.30, "ok"),
            pg_written=True,
        )

        class _FailingWriter:
            def __init__(self) -> None:
                self.write_calls: list[str] = []

            async def write(self, concept: ConceptExtractionSchema) -> WriteResult:
                self.write_calls.append(concept.concept_name)
                if concept.concept_name == "ConceptB":
                    raise RuntimeError("simulated failure")
                return ok_result

        failing_writer = _FailingWriter()

        summary = await run_link_resolve("sess-fail", pg, failing_writer)

        assert summary["NEW"] == 2, f"실패 1 제외 → 성공 2 기대, actual={summary}"
        assert "ConceptA" in failing_writer.write_calls
        assert "ConceptB" in failing_writer.write_calls
        assert "ConceptC" in failing_writer.write_calls

    @pytest.mark.anyio
    async def test_R06_mixed_actions_correct_summary(self) -> None:
        """Arrange: MERGE×1 + RELATED_TO×1 + NEW×2 = 4개 DRAFT 행
        Act: run_link_resolve
        Assert: summary == {"MERGE":1, "RELATED_TO":1, "NEW":2}
        """
        specs = [
            ("CsrfVariant",  MergeAction.MERGE,      "CSRF", 0.92),
            ("SsrfVariant",  MergeAction.RELATED_TO, "CSRF", 0.80),
            ("NewConcept1",  MergeAction.NEW,         None,   0.40),
            ("NewConcept2",  MergeAction.NEW,         None,   0.35),
        ]
        rows = [_staging_row(_make_concept(name)) for name, *_ in specs]
        pg = _FakeStagingPgPool(rows)

        results: dict[str, WriteResult] = {
            name: WriteResult(
                resolve=ResolveResult(action, target, score, name),
                pg_written=(action != MergeAction.MERGE),
            )
            for name, action, target, score in specs
        }
        writer = _FakeGraphWriterService(results)

        summary = await run_link_resolve("sess-mixed", pg, writer)

        assert summary == {"MERGE": 1, "RELATED_TO": 1, "NEW": 2}, f"집계 불일치: {summary}"

    @pytest.mark.anyio
    async def test_R07_summary_keys_are_string_values_of_merge_action(self) -> None:
        """run_link_resolve 반환 dict 키는 MergeAction.value (str) 이어야 함.

        Arrange: NEW 1건
        Act: run_link_resolve
        Assert: summary keys == {"MERGE", "RELATED_TO", "NEW"}
        """
        concept = _make_concept("SomeNewConcept")
        row = _staging_row(concept)
        pg = _FakeStagingPgPool([row])
        writer = _FakeGraphWriterService({
            "SomeNewConcept": WriteResult(
                resolve=ResolveResult(MergeAction.NEW, None, 0.20, "SomeNewConcept"),
                pg_written=True,
            )
        })

        summary = await run_link_resolve("sess-keys", pg, writer)

        assert set(summary.keys()) == {"MERGE", "RELATED_TO", "NEW"}, (
            f"summary keys 불일치: {set(summary.keys())}"
        )
        assert all(isinstance(v, int) for v in summary.values()), "summary values는 int여야 함"
