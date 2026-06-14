"""하이브리드 3-Factor 유사도 Resolver — JaroWinkler + Cosine 벡터."""

from __future__ import annotations

import hashlib
import math
import random
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import asyncpg
import httpx
import jellyfish

from app.core.config import OLLAMA_BASE_URL, EMBEDDING_MODEL, USE_REAL_LLM, pg_dsn

MERGE_THRESHOLD = 0.88
RELATED_THRESHOLD = 0.72
NAME_VECTOR_THRESHOLD = 0.8
DESC_VECTOR_THRESHOLD = 0.8


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

        incoming_names = _normalize_name_set([name] + aliases)

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

            # [트랙 A - 1단계] 1:1 텍스트 완전 매칭 (정규화 후 비교)
            if _normalize_name(name) == _normalize_name(existing_name):
                return ResolveResult(
                    action=ResolveAction.MERGE,
                    score=1.0,
                    target_concept_name=existing_name,
                    score_jaro_winkler=1.0,
                    score_name_vector=1.0,
                    score_desc_vector=1.0,
                )

            # [트랙 A - 2단계] 별칭 리스트 추적 (양방향 정규화 교집합)
            existing_names = _normalize_name_set([existing_name] + existing_aliases)
            if incoming_names & existing_names:
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

            # [트랙 B] 완전 매칭 실패 + name_vector/desc_vector 유사도 모두 >= 0.8 → MERGE 확정
            if cos_name >= NAME_VECTOR_THRESHOLD and cos_desc >= DESC_VECTOR_THRESHOLD:
                action = ResolveAction.MERGE
                score = max(score, MERGE_THRESHOLD)
            else:
                # 트랙 A/B 미충족 시 MERGE로 격상되지 않음 (RELATED_TO/NEW만 가능)
                action = ResolveAction.RELATED_TO if score >= RELATED_THRESHOLD else ResolveAction.NEW

            if _candidate_rank(action, score) > _candidate_rank(best.action, best.score):
                best = ResolveResult(
                    action=action,
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
        new_description_ko: Optional[str] = None,
    ) -> None:
        """MERGE 확정 후 alias 풀 재임베딩 → PG name_vector UPDATE.

        new_description_ko가 주어지면 desc_vector도 함께 재인덱싱한다
        (extract_advanced.md §4C 벡터 스토어 동기화).

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

            name_vec = await _embed_async(corpus)
            if name_vec is None:
                raise RuntimeError(f"Centroid Shifting 재임베딩 실패: {concept_name}")
            name_vec_str = "[" + ",".join(f"{v:.6f}" for v in name_vec) + "]"

            desc_vec_str: Optional[str] = None
            if new_description_ko:
                desc_vec = await _embed_async(new_description_ko)
                if desc_vec is None:
                    raise RuntimeError(f"desc_vector 재임베딩 실패: {concept_name}")
                desc_vec_str = "[" + ",".join(f"{v:.6f}" for v in desc_vec) + "]"

            async with conn.transaction():
                if desc_vec_str is not None:
                    await conn.execute(
                        """
                        UPDATE concepts
                        SET name_vector = $1::vector, aliases = $2,
                            desc_vector = $3::vector, description_ko = $4,
                            updated_at = now()
                        WHERE concept_name = $5
                        """,
                        name_vec_str,
                        merged_pool,
                        desc_vec_str,
                        new_description_ko,
                        concept_name,
                    )
                else:
                    await conn.execute(
                        """
                        UPDATE concepts
                        SET name_vector = $1::vector, aliases = $2, updated_at = now()
                        WHERE concept_name = $3
                        """,
                        name_vec_str,
                        merged_pool,
                        concept_name,
                    )
        finally:
            await conn.close()


# ── 유틸리티 ───────────────────────────────────────────────────────────────────

_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_name(s: str) -> str:
    """소문자 변환 + 모든 공백 제거 (1단계 완전 매칭용 정규화)."""
    return _WHITESPACE_RE.sub("", s.lower())


def _normalize_name_set(names: list[str]) -> set[str]:
    """이름/별칭 목록을 정규화하여 집합으로 변환 (2단계 별칭 교집합 비교용)."""
    return {_normalize_name(n) for n in names}


def _candidate_rank(action: "ResolveAction", score: float) -> tuple[int, float]:
    """후보 우선순위 — MERGE(Track B) > RELATED_TO > NEW, 동일 등급 내에서는 score로 비교."""
    priority = {ResolveAction.MERGE: 2, ResolveAction.RELATED_TO: 1, ResolveAction.NEW: 0}
    return (priority[action], score)


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


EMBEDDING_DIM = 1024


def _mock_embed_vector(text: str) -> list[float]:
    """USE_MOCK_LLM=true일 때 Ollama 호출 없이 결정적 임베딩 생성."""
    seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16) % (2**32)
    rng = random.Random(seed)
    vec = [rng.uniform(-1.0, 1.0) for _ in range(EMBEDDING_DIM)]
    norm = math.sqrt(sum(v * v for v in vec))
    return [v / norm for v in vec]


async def _embed_async(text: str) -> Optional[list[float]]:
    """Ollama embedding API 비동기 호출. USE_MOCK_LLM=true이면 결정적 mock 벡터 반환."""
    if not USE_REAL_LLM:
        return _mock_embed_vector(text)
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
