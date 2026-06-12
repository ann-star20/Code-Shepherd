"""하이브리드 3-Factor 유사도 Resolver — JaroWinkler + Cosine 벡터."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import asyncpg
import httpx
import jellyfish

from app.core.config import OLLAMA_BASE_URL, EMBEDDING_MODEL, pg_dsn

MERGE_THRESHOLD = 0.88
RELATED_THRESHOLD = 0.72


class ResolveAction(str, Enum):
    MERGE = "MERGE"
    RELATED_TO = "RELATED_TO"
    NEW = "NEW"


@dataclass
class ResolveResult:
    action: ResolveAction
    score: float
    target_concept_name: Optional[str]
    score_jaro_winkler: float
    score_name_vector: float
    score_desc_vector: float


class HybridResolver:
    """3-Factor 유사도 기반 그래프 MERGE/RELATED_TO/NEW 결정기."""

    def __init__(self, dsn: Optional[str] = None) -> None:
        self._dsn = dsn or pg_dsn()

    async def resolve(
        self,
        name: str,
        aliases: list[str],
        name_vector: list[float],
        desc_vector: Optional[list[float]],
    ) -> ResolveResult:
        """PG concepts 테이블과 비교하여 최고 점수 결정."""
        conn = await asyncpg.connect(self._dsn)
        try:
            candidates = await conn.fetch(
                """
                SELECT concept_name, aliases,
                       name_vector::text, desc_vector::text
                FROM concepts
                WHERE is_deprecated = false
                """
            )
        finally:
            await conn.close()

        incoming_lower = [a.lower() for a in ([name] + aliases)]

        best = ResolveResult(
            action=ResolveAction.NEW,
            score=0.0,
            target_concept_name=None,
            score_jaro_winkler=0.0,
            score_name_vector=0.0,
            score_desc_vector=0.0,
        )

        for row in candidates:
            existing_name: str = row["concept_name"]
            existing_aliases: list[str] = list(row["aliases"] or [])

            # 사전 dedup 단축경로 — alias 정확 일치 시 score=1.0 즉시 MERGE
            existing_lower = [existing_name.lower()] + [a.lower() for a in existing_aliases]
            if any(a in existing_lower for a in incoming_lower):
                return ResolveResult(
                    action=ResolveAction.MERGE,
                    score=1.0,
                    target_concept_name=existing_name,
                    score_jaro_winkler=1.0,
                    score_name_vector=1.0,
                    score_desc_vector=1.0,
                )

            jw = _jaro_winkler_max(name, aliases, existing_name, existing_aliases)

            existing_nv = _parse_pg_vector(row["name_vector"])
            cos_name = (
                _cosine(name_vector, existing_nv)
                if existing_nv and name_vector
                else 0.0
            )

            existing_dv = _parse_pg_vector(row["desc_vector"])
            cos_desc = (
                _cosine(desc_vector, existing_dv)
                if existing_dv and desc_vector
                else 0.0
            )

            score = jw * 0.4 + cos_name * 0.3 + cos_desc * 0.3

            if score > best.score:
                best = ResolveResult(
                    action=_action_from_score(score),
                    score=score,
                    target_concept_name=existing_name,
                    score_jaro_winkler=jw,
                    score_name_vector=cos_name,
                    score_desc_vector=cos_desc,
                )

        return best

    async def do_centroid_shift(
        self,
        concept_name: str,
        new_aliases: list[str],
    ) -> None:
        """MERGE 확정 후 alias 풀 재임베딩 → PG name_vector UPDATE.

        Centroid Shifting: 재임베딩 실패 시 트랜잭션 롤백으로 PG/Neo4j alias 불일치 방지.
        """
        conn = await asyncpg.connect(self._dsn)
        try:
            row = await conn.fetchrow(
                "SELECT aliases FROM concepts WHERE concept_name = $1", concept_name
            )
            if row is None:
                return
            existing: list[str] = list(row["aliases"] or [])
            merged_pool = list(dict.fromkeys([concept_name] + existing + new_aliases))
            corpus = " ".join(merged_pool)

            vec = await _embed_async(corpus)
            if vec is None:
                raise RuntimeError(f"Centroid Shifting 재임베딩 실패: {concept_name}")

            vec_str = "[" + ",".join(f"{v:.6f}" for v in vec) + "]"
            async with conn.transaction():
                await conn.execute(
                    """
                    UPDATE concepts
                    SET name_vector = $1::vector, aliases = $2, updated_at = now()
                    WHERE concept_name = $3
                    """,
                    vec_str,
                    merged_pool,
                    concept_name,
                )
        finally:
            await conn.close()


# ── 유틸리티 ───────────────────────────────────────────────────────────────────

def _jaro_winkler_max(
    name: str,
    aliases: list[str],
    existing_name: str,
    existing_aliases: list[str],
) -> float:
    """JaroWinkler 최고점 — 대소문자 무시, alias 1:1 전수 비교."""
    pool_a = [name.lower()] + [a.lower() for a in aliases]
    pool_b = [existing_name.lower()] + [a.lower() for a in existing_aliases]
    best = 0.0
    for a in pool_a:
        for b in pool_b:
            s = jellyfish.jaro_winkler_similarity(a, b)
            if s > best:
                best = s
    return best


def _cosine(v1: list[float], v2: list[float]) -> float:
    """L2 정규화 벡터 내적 기반 코사인 유사도."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    mag1 = math.sqrt(sum(a * a for a in v1))
    mag2 = math.sqrt(sum(b * b for b in v2))
    if mag1 == 0.0 or mag2 == 0.0:
        return 0.0
    return dot / (mag1 * mag2)


def _parse_pg_vector(text: Optional[str]) -> Optional[list[float]]:
    """PG vector 텍스트 '[0.1,0.2,...]' → list[float]."""
    if not text:
        return None
    try:
        return [float(x) for x in text.strip("[]").split(",")]
    except (ValueError, AttributeError):
        return None


def _action_from_score(score: float) -> ResolveAction:
    if score >= MERGE_THRESHOLD:
        return ResolveAction.MERGE
    if score >= RELATED_THRESHOLD:
        return ResolveAction.RELATED_TO
    return ResolveAction.NEW


async def _embed_async(text: str) -> Optional[list[float]]:
    """Ollama embedding API 비동기 호출."""
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{OLLAMA_BASE_URL}/api/embeddings",
                json={"model": EMBEDDING_MODEL, "prompt": text},
            )
            resp.raise_for_status()
            vec: list[float] = resp.json()["embedding"]
            return vec if len(vec) == 1024 else None
    except Exception:
        return None
