"""hybrid_resolver.py — 3-Factor 하이브리드 링크 리졸버 (build_process.md §1)

구형 SAME_AS 관계선 완전 폐기.

하이브리드 점수 공식:
  Score = (JaroWinkler × 0.4) + (CosineName × 0.3) + (CosineDesc × 0.3)

분기 규칙:
  Score >= 0.88  → MERGE   : 기존 노드에 병합 + Centroid Shifting (name_vector 재임베딩)
  0.72 <= S < 0.88 → RELATED_TO : [:RELATED_TO] 엣지로 연결
  Score < 0.72   → NEW     : 완전 신규 마스터 노드 (호출자가 MERGE 책임)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

import asyncpg
import neo4j

from app.domain.models import ConceptExtractionSchema

# ── 임계치 ─────────────────────────────────────────────────────────────────────
MERGE_THRESHOLD = 0.88
RELATED_THRESHOLD = 0.72

# ── 가중치 ─────────────────────────────────────────────────────────────────────
WEIGHT_JW = 0.4
WEIGHT_NAME = 0.3
WEIGHT_DESC = 0.3


# ── 결과 타입 ──────────────────────────────────────────────────────────────────


class MergeAction(str, Enum):
    MERGE = "MERGE"  # score >= 0.88
    RELATED_TO = "RELATED_TO"  # 0.72 <= score < 0.88
    NEW = "NEW"  # score < 0.72


@dataclass
class ResolveResult:
    action: MergeAction
    target: str | None  # 기존 마스터 노드명 (NEW일 때 None)
    score: float
    incoming_name: str
    score_metrics: dict = None  # {"jaro": float, "name_vec": float, "desc_vec": float}

    def __post_init__(self):
        if self.score_metrics is None:
            self.score_metrics = {"jaro": 0.0, "name_vec": 0.0, "desc_vec": 0.0}


class EmbeddingProtocol(Protocol):
    def embed(self, text: str) -> list[float]: ...


# ── 순수 함수: Jaro-Winkler ────────────────────────────────────────────────────


def _jaro(s1: str, s2: str) -> float:
    if s1 == s2:
        return 1.0
    len1, len2 = len(s1), len(s2)
    if not len1 or not len2:
        return 0.0
    match_dist = max(len1, len2) // 2 - 1
    match_dist = max(0, match_dist)
    flags1 = [False] * len1
    flags2 = [False] * len2
    matches = 0
    for i in range(len1):
        lo = max(0, i - match_dist)
        hi = min(i + match_dist + 1, len2)
        for j in range(lo, hi):
            if not flags2[j] and s1[i] == s2[j]:
                flags1[i] = flags2[j] = True
                matches += 1
                break
    if not matches:
        return 0.0
    k = t = 0
    for i in range(len1):
        if not flags1[i]:
            continue
        while not flags2[k]:
            k += 1
        if s1[i] != s2[k]:
            t += 1
        k += 1
    return (matches / len1 + matches / len2 + (matches - t / 2) / matches) / 3


def _jaro_winkler(s1: str, s2: str, p: float = 0.1) -> float:
    jaro = _jaro(s1, s2)
    prefix = 0
    for c1, c2 in zip(s1[:4], s2[:4]):
        if c1 == c2:
            prefix += 1
        else:
            break
    return jaro + prefix * p * (1.0 - jaro)


def max_jaro_winkler(pool_a: list[str], pool_b: list[str]) -> float:
    """두 별칭 풀 간 Jaro-Winkler 최고점 추출 (대소문자 무시, 0~1.0).

    build_process.md §1: 대소문자/공백을 무시하고 aliases 배열을 1:1로 비교해 최고점 추출.
    """
    if not pool_a or not pool_b:
        return 0.0
    best = 0.0
    for a in pool_a:
        for b in pool_b:
            s = _jaro_winkler(a.lower(), b.lower())
            if s > best:
                best = s
    return best


# ── 순수 함수: 점수 계산 ───────────────────────────────────────────────────────


def compute_hybrid_score(jw: float, name_cos: float, desc_cos: float) -> float:
    """3-Factor 선형 결합 점수 (build_process.md §1 공식)."""
    return jw * WEIGHT_JW + name_cos * WEIGHT_NAME + desc_cos * WEIGHT_DESC


def _cosine(a: list[float], b: list[float]) -> float:
    """L2-정규화된 벡터의 코사인 유사도 = 내적."""
    return max(-1.0, min(1.0, sum(x * y for x, y in zip(a, b))))


# ── 벡터 직렬화 (asyncpg ↔ pgvector) ─────────────────────────────────────────


def _vec_to_str(vec: list[float]) -> str:
    """asyncpg pgvector $1::vector 캐스팅용 문자열 표현."""
    return "[" + ",".join(f"{x:.8f}" for x in vec) + "]"


def _parse_vec(v: Any) -> list[float]:
    """asyncpg가 반환하는 pgvector 값을 float list로 변환.

    - asyncpg 기본: "[0.1,0.2,...]" 문자열 반환
    - FakePgPool: list[float] 직접 반환
    """
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return [float(x) for x in v]
    s = str(v).strip()
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1]
        return [float(x) for x in inner.split(",") if x.strip()]
    return []


# ── 핵심 엔진 ─────────────────────────────────────────────────────────────────


async def hybrid_resolve(
    incoming: ConceptExtractionSchema,
    pg_pool: asyncpg.Pool,
    neo4j_driver: neo4j.AsyncDriver,
    embedding_svc: EmbeddingProtocol,
) -> ResolveResult:
    """3-Factor 하이브리드 점수로 유입 개념의 귀속 액션을 결정한다.

    0. (선처리) PG aliases 배열 정확 히트 → 벡터 계산 없이 확정 MERGE
    1. 유입 개념의 name_vec, desc_vec 임베딩
    2. PostgreSQL 기존 마스터 노드 전체 스캔
    3. 각 후보와 하이브리드 점수 계산 → 최고점 후보 선정
    4. 점수 기반 분기 실행 (MERGE / RELATED_TO / NEW)
    """
    # 0. concept_name이 기존 노드의 aliases 배열에 정확히 존재하면 확정 MERGE
    #    MockEmbeddingService(BoW) 환경에서 cosine 점수가 낮아 임계치 미달하는 경우를
    #    벡터 계산 이전에 차단한다.
    alias_hit = await pg_pool.fetchrow(
        "SELECT concept_name FROM concepts "
        "WHERE $1 = ANY(aliases) "
        "AND (is_deprecated IS NOT TRUE OR is_deprecated IS NULL) "
        "LIMIT 1",
        incoming.concept_name,
    )
    if alias_hit:
        target = alias_hit["concept_name"]
        in_name_vec = embedding_svc.embed(
            ", ".join([incoming.concept_name] + incoming.aliases)
        )
        await _do_merge(
            incoming, target, in_name_vec, pg_pool, neo4j_driver, embedding_svc
        )
        return ResolveResult(MergeAction.MERGE, target, 1.0, incoming.concept_name)

    in_name_text = ", ".join([incoming.concept_name] + incoming.aliases)
    in_desc_text = incoming.description_ko or incoming.concept_name
    in_name_vec = embedding_svc.embed(in_name_text)
    in_desc_vec = embedding_svc.embed(in_desc_text)
    in_pool = [incoming.concept_name] + incoming.aliases

    rows = await pg_pool.fetch(
        "SELECT concept_name, aliases, name_vector, desc_vector "
        "FROM concepts WHERE is_deprecated IS NOT TRUE"
    )

    best_score: float = 0.0
    best_target: str | None = None

    for row in rows:
        ex_pool = [row["concept_name"]] + list(row["aliases"] or [])
        jw = max_jaro_winkler(in_pool, ex_pool)
        ex_name_v = _parse_vec(row["name_vector"])
        ex_desc_v = _parse_vec(row["desc_vector"])
        name_cos = _cosine(in_name_vec, ex_name_v) if ex_name_v else 0.0
        desc_cos = _cosine(in_desc_vec, ex_desc_v) if ex_desc_v else 0.0
        score = compute_hybrid_score(jw, name_cos, desc_cos)

        if score > best_score:
            best_score = score
            best_target = row["concept_name"]

    if best_score >= MERGE_THRESHOLD and best_target:
        await _do_merge(
            incoming,
            best_target,
            in_name_vec,
            pg_pool,
            neo4j_driver,
            embedding_svc,
        )
        return ResolveResult(
            MergeAction.MERGE, best_target, best_score, incoming.concept_name
        )

    if best_score >= RELATED_THRESHOLD and best_target:
        await _do_related_to(incoming.concept_name, best_target, neo4j_driver)
        return ResolveResult(
            MergeAction.RELATED_TO, best_target, best_score, incoming.concept_name
        )

    return ResolveResult(MergeAction.NEW, None, best_score, incoming.concept_name)


async def _do_merge(
    incoming: ConceptExtractionSchema,
    target_name: str,
    _incoming_name_vec: list[float],  # 현재는 재임베딩으로 대체되므로 미사용
    pg_pool: asyncpg.Pool,
    neo4j_driver: neo4j.AsyncDriver,
    embedding_svc: EmbeddingProtocol,
) -> None:
    """MERGE 분기: aliases 통합 + name_vector Centroid Shifting.

    Centroid Shifting:
      기존 노드의 aliases에 신규 이름/별칭을 추가 후,
      확장된 키워드 풀 전체를 다시 임베딩하여 name_vector의 '중심점'을 이동.
    """
    row = await pg_pool.fetchrow(
        "SELECT aliases, domains, desc_vector, description_ko "
        "FROM concepts WHERE concept_name = $1",
        target_name,
    )
    existing_aliases: list[str] = list(row["aliases"] or []) if row else []
    existing_domains: list[str] = list(row["domains"] or []) if row else []
    existing_desc_ko = row["description_ko"] if row else None

    new_entries = [incoming.concept_name] + incoming.aliases
    merged = list(dict.fromkeys(existing_aliases + new_entries))  # 순서 보존 dedup
    merged_domain = list(dict.fromkeys(existing_domains + incoming.domains))

    # Centroid Shifting: 확장된 키워드 풀로 재임베딩
    shifted_vec = embedding_svc.embed(", ".join([target_name] + merged))

    eff_severity = "low" if incoming.severity == "info" else incoming.severity

    desc_vec_str = None
    if incoming.description_ko and not existing_desc_ko:
        desc_vec_str = _vec_to_str(embedding_svc.embed(incoming.description_ko))

    await pg_pool.execute(
        """
        UPDATE concepts
        SET aliases        = $1,
            domains        = $2,
            name_vector    = $3::vector,
            severity       = COALESCE($4, severity),
            description_ko = COALESCE($5, description_ko),
            concept_type   = COALESCE($6, concept_type),
            cwe_id         = COALESCE($7, cwe_id),
            owasp_id       = COALESCE($8, owasp_id),
            root_cause     = COALESCE($9, root_cause),
            desc_vector    = COALESCE($10::vector, desc_vector),
            updated_at     = now()
        WHERE concept_name = $11
        """,
        merged,
        merged_domain,
        _vec_to_str(shifted_vec),
        eff_severity,
        incoming.description_ko or None,
        incoming.concept_type,
        incoming.cwe_id,
        incoming.owasp_id,
        incoming.root_cause,
        desc_vec_str,
        target_name,
    )

    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (c:Concept {name: $name}) "
            "SET c.aliases    = apoc.coll.toSet(c.aliases + $new_aliases), "
            "    c.updated_at = timestamp()",
            name=target_name,
            new_aliases=merged,
        )


async def _do_related_to(
    incoming_name: str,
    target_name: str,
    neo4j_driver: neo4j.AsyncDriver,
) -> None:
    """RELATED_TO 분기: 두 Concept 사이에 [:RELATED_TO] 엣지를 멱등하게 생성."""
    async with neo4j_driver.session() as session:
        await session.run(
            "MERGE (a:Concept {name: $a}) "
            "MERGE (b:Concept {name: $b}) "
            "MERGE (a)-[:RELATED_TO]-(b)",
            a=incoming_name,
            b=target_name,
        )


async def compute_resolve_score(
    incoming: ConceptExtractionSchema,
    pg_pool: asyncpg.Pool,
    embedding_svc: EmbeddingProtocol,
) -> ResolveResult:
    """3-Factor 점수와 액션을 반환 — PG/Neo4j에 아무것도 쓰지 않는다 (순수 계산).

    _do_extract에서 staging 저장 직후 호출하여 infer_action/infer_score를 결정한다.
    실제 MERGE Centroid Shifting과 Neo4j [:RELATED_TO] 엣지는 write_graph_task에서 수행.

    0. (선처리) PG aliases 배열 정확 히트 → score=1.0 확정 MERGE 반환 (벡터 계산 생략)
    """
    # 0. concept_name이 기존 노드의 aliases에 정확히 포함되면 확정 MERGE (score=1.0)
    alias_hit = await pg_pool.fetchrow(
        "SELECT concept_name FROM concepts "
        "WHERE $1 = ANY(aliases) "
        "AND (is_deprecated IS NOT TRUE OR is_deprecated IS NULL) "
        "LIMIT 1",
        incoming.concept_name,
    )
    if alias_hit:
        return ResolveResult(
            MergeAction.MERGE, alias_hit["concept_name"], 1.0, incoming.concept_name
        )

    in_name_text = ", ".join([incoming.concept_name] + incoming.aliases)
    in_desc_text = incoming.description_ko or incoming.concept_name
    in_name_vec = embedding_svc.embed(in_name_text)
    in_desc_vec = embedding_svc.embed(in_desc_text)
    in_pool = [incoming.concept_name] + incoming.aliases

    rows = await pg_pool.fetch(
        "SELECT concept_name, aliases, name_vector, desc_vector "
        "FROM concepts WHERE is_deprecated IS NOT TRUE"
    )

    best_score: float = 0.0
    best_target: str | None = None

    for row in rows:
        ex_pool = [row["concept_name"]] + list(row["aliases"] or [])
        jw = max_jaro_winkler(in_pool, ex_pool)
        ex_name_v = _parse_vec(row["name_vector"])
        ex_desc_v = _parse_vec(row["desc_vector"])
        name_cos = _cosine(in_name_vec, ex_name_v) if ex_name_v else 0.0
        desc_cos = _cosine(in_desc_vec, ex_desc_v) if ex_desc_v else 0.0
        score = compute_hybrid_score(jw, name_cos, desc_cos)

        if score > best_score:
            best_score = score
            best_target = row["concept_name"]

    if best_score >= MERGE_THRESHOLD and best_target:
        return ResolveResult(
            MergeAction.MERGE, best_target, best_score, incoming.concept_name
        )
    if best_score >= RELATED_THRESHOLD and best_target:
        return ResolveResult(
            MergeAction.RELATED_TO, best_target, best_score, incoming.concept_name
        )
    return ResolveResult(MergeAction.NEW, None, best_score, incoming.concept_name)
