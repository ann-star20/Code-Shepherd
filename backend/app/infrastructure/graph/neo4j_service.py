"""GraphWriterService — hybrid_resolve → 4-레이어 PG + Neo4j 적재.

PRD §11 Graph Writer Agent:
  ConceptExtractionSchema → hybrid_resolve(MERGE/RELATED_TO/NEW) → 멱등 적재

액션별 처리:
  MERGE      → _do_merge: PG aliases + Centroid Shifting, Neo4j aliases 갱신 자동 완료
               GraphWriterService는 추가 PG/Neo4j 쓰기 없이 로그만 기록
  RELATED_TO → 신규 노드 PG INSERT + Neo4j 4-레이어 MERGE
               [:RELATED_TO] 엣지는 hybrid_resolve._do_related_to 에서 이미 생성
  NEW        → 완전 신규 PG INSERT + Neo4j 4-레이어 MERGE
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import asyncpg
import neo4j

from app.adapters.db.neo4j_repo import Neo4jConceptRepo
from app.domain.models import ConceptExtractionSchema
from app.infrastructure.graph.hybrid_resolver import (
    EmbeddingProtocol,
    MergeAction,
    ResolveResult,
    _do_merge,
    _do_related_to,
    _vec_to_str,
    hybrid_resolve,
)

log = logging.getLogger(__name__)


@dataclass
class WriteResult:
    resolve: ResolveResult
    pg_written: bool  # NEW / RELATED_TO 시 True, MERGE 시 False


class GraphWriterService:
    """hybrid_resolve 분기 → PG concepts + Neo4j 4-레이어 멱등 적재."""

    def __init__(
        self,
        pg_pool: asyncpg.Pool,
        neo4j_driver: neo4j.AsyncDriver,
        neo4j_repo: Neo4jConceptRepo,
        embedding_svc: EmbeddingProtocol,
    ) -> None:
        self._pg = pg_pool
        self._driver = neo4j_driver
        self._repo = neo4j_repo
        self._emb = embedding_svc

    async def write(self, concept: ConceptExtractionSchema) -> WriteResult:
        """hybrid_resolve 분기 후 PG/Neo4j 적재.

        MERGE:
          _do_merge가 PG Centroid Shifting + Neo4j aliases 갱신을 완료했으므로
          추가 작업 없이 WriteResult(pg_written=False) 반환.
        RELATED_TO:
          신규 노드를 PG + Neo4j에 생성.
          [:RELATED_TO] 엣지는 hybrid_resolve._do_related_to에서 이미 조인됨.
        NEW:
          완전 신규 PG INSERT + Neo4j 4-레이어 MERGE.
        """
        result = await hybrid_resolve(
            concept, self._pg, self._driver, self._emb
        )
        pg_written = False

        if result.action == MergeAction.MERGE:
            # Centroid Shifting은 hybrid_resolve 내부에서 완료됨.
            # Mechanism/CodeExample은 별도로 target 노드에 병합해야 함.
            if concept.mechanisms and result.target:
                await self._repo.merge_mechanisms(concept, result.target)
            log.info(
                "[gw] MERGE '%s' → '%s' (score=%.4f)",
                result.incoming_name, result.target, result.score,
            )
        else:
            await self._upsert_pg(concept)
            await self._repo.merge_concept(concept)
            pg_written = True
            log.info(
                "[gw] %s '%s' (score=%.4f, target=%s)",
                result.action.value, result.incoming_name,
                result.score, result.target,
            )

        return WriteResult(resolve=result, pg_written=pg_written)

    async def write_with_precomputed(
        self,
        concept: ConceptExtractionSchema,
        resolve_result: ResolveResult,
    ) -> WriteResult:
        """사전 계산된 ResolveResult로 적재 — hybrid_resolve 재호출(재스코어링) 없음.

        _do_write_graph가 staging_concepts.infer_action을 읽어 호출한다.
        Centroid Shifting과 [:RELATED_TO] 엣지 생성은 그대로 수행한다.
        """
        pg_written = False

        if resolve_result.action == MergeAction.MERGE:
            in_name_vec = self._emb.embed(
                ", ".join([concept.concept_name] + concept.aliases)
            )
            await _do_merge(
                concept, resolve_result.target, in_name_vec,
                self._pg, self._driver, self._emb,
            )
            # Mechanism/CodeExample을 target 노드에 병합
            if concept.mechanisms and resolve_result.target:
                await self._repo.merge_mechanisms(concept, resolve_result.target)
            log.info(
                "[gw] MERGE(pre) '%s' → '%s' (score=%.4f)",
                resolve_result.incoming_name, resolve_result.target, resolve_result.score,
            )
        else:
            await self._upsert_pg(concept)
            await self._repo.merge_concept(concept)
            pg_written = True
            if resolve_result.action == MergeAction.RELATED_TO and resolve_result.target:
                await _do_related_to(concept.concept_name, resolve_result.target, self._driver)
            log.info(
                "[gw] %s(pre) '%s' (score=%.4f, target=%s)",
                resolve_result.action.value, resolve_result.incoming_name,
                resolve_result.score, resolve_result.target,
            )

        return WriteResult(resolve=resolve_result, pg_written=pg_written)

    async def _upsert_pg(self, concept: ConceptExtractionSchema) -> None:
        """concepts 테이블 멱등성 INSERT + 벡터 충전.

        ON CONFLICT(concept_name): domains/aliases 배열 합집합 갱신,
        root_cause/벡터는 기존 값 우선(COALESCE).
        name_vector = embed(concept_name + aliases 전체 풀)
        desc_vector = embed(description_ko) — 없으면 NULL 유지
        """
        sev = "low" if concept.severity == "info" else (concept.severity or "medium")

        name_corpus  = ", ".join([concept.concept_name] + concept.aliases)
        name_vec_str = _vec_to_str(self._emb.embed(name_corpus))
        desc_vec_str = (
            _vec_to_str(self._emb.embed(concept.description_ko))
            if concept.description_ko else None
        )

        await self._pg.execute(
            """
            INSERT INTO concepts
                (concept_name, doc_id, domains, severity, description_ko,
                 concept_type, cwe_id, owasp_id, aliases, root_cause,
                 name_vector, desc_vector)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::vector, $12::vector)
            ON CONFLICT (concept_name) DO UPDATE
            SET domains        = (SELECT array(
                                    SELECT DISTINCT unnest(concepts.domains || EXCLUDED.domains)
                                  )),
                severity       = EXCLUDED.severity,
                description_ko = EXCLUDED.description_ko,
                aliases        = (SELECT array(
                                    SELECT DISTINCT unnest(concepts.aliases || EXCLUDED.aliases)
                                  )),
                root_cause     = COALESCE(EXCLUDED.root_cause, concepts.root_cause),
                name_vector    = COALESCE(EXCLUDED.name_vector, concepts.name_vector),
                desc_vector    = COALESCE(EXCLUDED.desc_vector, concepts.desc_vector),
                updated_at     = NOW()
            """,
            concept.concept_name,
            concept.doc_id,
            concept.domains,
            sev,
            concept.description_ko,
            concept.concept_type,
            concept.cwe_id,
            concept.owasp_id,
            concept.aliases,
            concept.root_cause,
            name_vec_str,
            desc_vec_str,
        )
