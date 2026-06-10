"""
vector_search 노드 — pgVector RAG 유사 이슈 검색

이 노드는 CLI 도구가 탐지한 raw 이슈에 과거 유사 이슈를 주입(enrichment)한다.
주입된 similar_issues는 llm_judge 노드의 RAG context로 사용된다.

흐름:
    static_raw + security_raw  →  (이슈 메시지 임베딩)  →  pgVector 코사인 검색
                                  →  similar_issues 주입  →  enriched

pgVector 쿼리:
    SELECT pr_id, content, 1-(embedding <=> $1::vector) AS similarity
    FROM chunk_embeddings
    WHERE 1-(embedding <=> $1::vector) >= SIMILARITY_THRESHOLD
    ORDER BY embedding <=> $1::vector
    LIMIT TOP_K

임베딩:
    USE_MOCK_LLM=true  → 해시 기반 결정적(deterministic) Mock 벡터 반환
    USE_MOCK_LLM=false → bge-m3 (BAAI/bge-m3) 로컬 임베딩, 1024차원
                         ⚠️ 팀 chunk_embeddings가 bge-m3/1024로 적재돼 있으므로
                            질의도 반드시 동일 모델·차원이어야 유사도가 의미를 가진다
                            (OpenAI 등 다른 모델은 벡터 공간이 달라 매칭 무의미)

CLAUDE.md 준수:
    §8   임베딩 차원 통일 (PGVECTOR_DIMENSION 환경변수)
    §12  pgVector 0결과 → 빈 리스트 반환 (예외 던지지 않음)
    §6   파라미터 바인딩만 사용 (f-string SQL 금지)
    §9   팀 표준: pgVector (Milvus 금지)
"""

import asyncio
import hashlib
import logging
import os
from typing import Any, TYPE_CHECKING

# asyncpg는 실제 DB 연결 시에만 필요 (USE_MOCK_LLM=false + POSTGRES_URL 설정 시)
# 개발 환경(Mock 모드)에서는 미설치 상태일 수 있으므로 lazy import 사용
# → import 시점이 아닌 _get_pool() 호출 시점에 import (CLAUDE.md §10-3)
if TYPE_CHECKING:
    import asyncpg  # type checker용 (런타임에는 실행되지 않음)

from dev2.schema import Dev2State

logger = logging.getLogger(__name__)

# ── pgVector 검색 파라미터 ──────────────────────────────────────────────────────
# 유사도 threshold: 0.7 미만은 "무관한 사례"로 필터링
# top-k: 이슈당 최대 참조 과거 사례 수
SIMILARITY_THRESHOLD = float(os.getenv("VECTOR_SIMILARITY_THRESHOLD", "0.7"))
TOP_K = int(os.getenv("VECTOR_TOP_K", "3"))

# 임베딩 차원 — CLAUDE.md §8: .env의 PGVECTOR_DIMENSION과 반드시 일치
# 팀 chunk_embeddings 실제 적재값 = bge-m3 / vector(1024)
EMBEDDING_DIM = int(os.getenv("PGVECTOR_DIMENSION", "1024"))

# bge-m3 임베딩 모델명 — chunk_embeddings.model_name과 동일해야 벡터 공간이 일치
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")

# pgVector 검색 SQL — $1: 쿼리 벡터(text), $2: LIMIT(int)
# CLAUDE.md §6: 파라미터 바인딩만 사용 (SQL 인젝션 방지)
_SEARCH_SQL = """
SELECT
    COALESCE(metadata->>'pr_id', chunk_id::text)  AS pr_id,
    content,
    1 - (embedding <=> $1::vector)                 AS similarity
FROM chunk_embeddings
WHERE 1 - (embedding <=> $1::vector) >= $2
ORDER BY embedding <=> $1::vector
LIMIT $3
"""


# ── 임베딩 생성 ────────────────────────────────────────────────────────────────

def _mock_embedding(text: str) -> list[float]:
    """
    결정적(deterministic) Mock 임베딩 반환.

    해시 기반으로 동일 텍스트 → 동일 벡터를 보장한다.
    → 테스트 재현성 확보 (같은 입력 → 같은 pgVector 쿼리)
    → CLAUDE.md §8: PGVECTOR_DIMENSION 길이와 반드시 일치

    Args:
        text: 임베딩할 텍스트

    Returns:
        EMBEDDING_DIM 길이의 float 리스트 (정규화됨)
    """
    # MD5 해시를 시드로 결정적 float 배열 생성
    digest = hashlib.md5(text.encode()).hexdigest()
    # 16진수 → 0~1 범위의 float 반복 생성
    seed_floats = [int(digest[i:i+2], 16) / 255.0 for i in range(0, 32, 2)]
    # EMBEDDING_DIM 길이로 반복 확장
    vec = [seed_floats[i % len(seed_floats)] for i in range(EMBEDDING_DIM)]
    # L2 정규화 (코사인 유사도 계산을 위해)
    norm = sum(x ** 2 for x in vec) ** 0.5 or 1.0
    return [x / norm for x in vec]


# ── bge-m3 실모델 로더 (팀 chunk_embeddings와 동일 모델) ──────────────────────
# SentenceTransformer 모델은 무겁다(~2.2GB) → 프로세스당 1회만 로드하는 lazy
# singleton. 동시 로드 경쟁을 막기 위해 asyncio.Lock으로 보호한다.
_bge_model: Any = None
_bge_lock = asyncio.Lock()


def _load_bge_model() -> Any:
    """sentence-transformers로 bge-m3 모델을 로드한다 (동기 — to_thread로 호출)."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(EMBEDDING_MODEL_NAME)


async def _get_bge_model() -> Any:
    """bge-m3 모델 싱글턴을 반환한다 (최초 호출 시에만 로드)."""
    global _bge_model
    if _bge_model is None:
        async with _bge_lock:
            if _bge_model is None:  # 락 획득 후 재확인 (double-checked locking)
                _bge_model = await asyncio.to_thread(_load_bge_model)
    return _bge_model


async def _embed_text(text: str, use_mock: bool) -> list[float]:
    """
    텍스트를 임베딩 벡터로 변환한다.

    USE_MOCK_LLM=true  → Mock 임베딩 (결정적, API 호출 없음)
    USE_MOCK_LLM=false → bge-m3 (BAAI/bge-m3) 로컬 임베딩, 1024차원

    Args:
        text: 임베딩할 이슈 메시지
        use_mock: True → Mock / False → 실제 API

    Returns:
        EMBEDDING_DIM 길이의 float 리스트
    """
    if use_mock:
        # to_thread: 순수 CPU 연산이지만 미래 실제 API 교체 시 비동기 일관성 유지
        return await asyncio.to_thread(_mock_embedding, text)

    # 실제 bge-m3 임베딩 (USE_MOCK_LLM=false) — 팀 chunk_embeddings와 동일 모델/공간
    try:
        model = await _get_bge_model()
        # encode는 CPU/GPU 바운드 → 이벤트 루프 블록 방지 위해 to_thread로 오프로드.
        # normalize_embeddings=True: 단위 벡터화 → pgVector 코사인 거리(<=>)와 정합.
        vec = await asyncio.to_thread(
            lambda: model.encode(text, normalize_embeddings=True).tolist()
        )
        # 차원 검증 (CLAUDE.md §8: 차원 불일치 → 즉시 에러 로그)
        if len(vec) != EMBEDDING_DIM:
            logger.error(
                "_embed_text: 임베딩 차원 불일치 expected=%d actual=%d — Mock으로 fallback",
                EMBEDDING_DIM, len(vec),
            )
            return _mock_embedding(text)
        return vec
    except Exception as exc:
        logger.error("_embed_text: bge-m3 임베딩 실패 — %s | Mock으로 fallback", exc)
        return _mock_embedding(text)


# ── pgVector 검색 ──────────────────────────────────────────────────────────────

def _vec_to_pg_str(vec: list[float]) -> str:
    """
    float 리스트를 pgVector 문자열 형식으로 변환.

    asyncpg는 Python list를 벡터 파라미터로 직접 받지 않는다.
    '[0.1,0.2,...]' 문자열 + ::vector 캐스팅을 사용해야 한다.

    Args:
        vec: float 리스트 (EMBEDDING_DIM 길이)

    Returns:
        '[0.1234,0.5678,...]' 형식 문자열
    """
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


async def _search_pgvector(
    query_vec: list[float],
    pool: Any,
) -> list[dict]:
    """
    pgVector로 유사 이슈를 검색한다.

    CLAUDE.md §12: 결과 0건 → 빈 리스트 반환 (예외 던지지 않음)
    CLAUDE.md §6: SQL 파라미터 바인딩 사용 (f-string SQL 조합 금지)

    Args:
        query_vec: 쿼리 벡터 (이슈 메시지 임베딩)
        pool: asyncpg 연결 풀 (외부 주입 — 테스트 시 Mock으로 교체 가능)

    Returns:
        [{"pr_id": str, "similarity": float, "message": str}, ...]
        유사도 SIMILARITY_THRESHOLD 이상, TOP_K 개 이내
    """
    vec_str = _vec_to_pg_str(query_vec)

    try:
        rows = await pool.fetch(_SEARCH_SQL, vec_str, SIMILARITY_THRESHOLD, TOP_K)
    except Exception as exc:
        # DB 연결 실패 → 0건처럼 처리 (파이프라인 중단 방지, CLAUDE.md §12)
        logger.error("_search_pgvector: DB 조회 실패 — %s | 빈 리스트 반환", exc)
        return []

    return [
        {
            "pr_id": row["pr_id"],
            "similarity": float(row["similarity"]),
            "message": row["content"],
        }
        for row in rows
    ]


async def _mock_search(message: str) -> list[dict]:
    """
    Mock pgVector 검색 결과 반환 — USE_MOCK_LLM=true + DB 없을 때 사용.

    결정적 결과: 메시지에 'SQL' 포함 시 SQL 관련 유사 사례,
    'complexity'/'복잡도' 포함 시 복잡도 관련 유사 사례를 반환한다.

    실제 사례와 동일한 {pr_id, similarity, message} 형식으로 반환.
    """
    msg_lower = message.lower()

    if any(kw in msg_lower for kw in ("sql", "injection", "인젝션", "파라미터")):
        return [
            {"pr_id": "PR-002", "similarity": 0.92, "message": "SQL 파라미터 미처리 — B608"},
            {"pr_id": "PR-005", "similarity": 0.78, "message": "SQL 인젝션 취약점 (user_input 직접 삽입)"},
        ]
    if any(kw in msg_lower for kw in ("complexity", "복잡도", "cyclomatic", "분기")):
        return [
            {"pr_id": "PR-001", "similarity": 0.85, "message": "순환복잡도 12 — 함수 분리 필요"},
        ]
    if any(kw in msg_lower for kw in ("n+1", "query", "쿼리")):
        return [
            {"pr_id": "PR-003", "similarity": 0.88, "message": "N+1 쿼리 — joinedload 사용 권장"},
        ]

    # 알 수 없는 패턴 → 유사 사례 없음 (CLAUDE.md §12: 예외 던지지 않음)
    return []


# ── 연결 풀 생성 ────────────────────────────────────────────────────────────────

async def _get_pool() -> Any:
    """
    asyncpg 연결 풀을 생성한다.

    POSTGRES_URL 미설정 or 연결 실패 시 None 반환 (Mock 모드 fallback).
    → 개발 환경에서 DB 없이도 파이프라인이 동작할 수 있도록.

    asyncpg는 실제 DB 연결 시에만 필요하므로 여기서 lazy import 한다.
    (Mock 모드에서는 이 함수가 호출되지 않거나 None을 반환하여 asyncpg 없이도 동작)

    Returns:
        asyncpg.Pool 또는 None (연결 실패 시)
    """
    postgres_url = os.getenv("POSTGRES_URL", "")
    if not postgres_url:
        logger.warning("_get_pool: POSTGRES_URL 미설정 — pgVector 검색 건너뜀")
        return None

    # asyncpg lazy import — USE_MOCK_LLM=false + POSTGRES_URL 설정 시에만 실행
    try:
        import asyncpg as _asyncpg  # noqa: PLC0415
    except ImportError:
        logger.error("_get_pool: asyncpg 미설치 — `pip install asyncpg`로 설치하세요 | Mock fallback")
        return None

    # asyncpg는 postgresql:// 스키마 사용 (SQLAlchemy의 postgresql+asyncpg:// 아님)
    url = postgres_url.replace("postgresql+asyncpg://", "postgresql://")

    try:
        pool = await _asyncpg.create_pool(url, min_size=1, max_size=5)
        logger.info("_get_pool: asyncpg 연결 풀 생성 완료")
        return pool
    except Exception as exc:
        logger.error("_get_pool: DB 연결 실패 — %s | pgVector 검색 건너뜀", exc)
        return None


# ── 핵심 enrichment 함수 ───────────────────────────────────────────────────────

async def _enrich_issue(
    issue: dict,
    use_mock: bool,
    pool: Any | None,
) -> dict:
    """
    단일 이슈에 pgVector 유사 이슈를 주입한다.

    흐름:
        1. 이슈 메시지 임베딩
        2. pgVector 검색 (pool이 있으면) 또는 Mock 검색
        3. similar_issues 필드를 추가한 새 dict 반환

    Args:
        issue: CLI 도구 원본 이슈 dict
        use_mock: True → Mock 임베딩+검색 / False → 실제 API+DB
        pool: asyncpg 연결 풀 (None이면 Mock으로 fallback)

    Returns:
        similar_issues 필드가 추가된 이슈 dict
    """
    message = issue.get("message", "")

    # Pool 없거나 Mock 모드면 Mock 검색 사용
    if use_mock or pool is None:
        if pool is None and not use_mock:
            logger.warning("_enrich_issue: DB 풀 없음 — Mock 검색으로 fallback")
        similar = await _mock_search(message)
    else:
        # 실제 pgVector 검색
        try:
            query_vec = await _embed_text(message, use_mock=False)
            similar = await _search_pgvector(query_vec, pool)
        except Exception as exc:
            logger.error("_enrich_issue: 이슈 enrichment 실패 — %s | 유사 사례 없음으로 처리", exc)
            similar = []

    if similar:
        logger.debug(
            "_enrich_issue: '%s' → 유사 사례 %d건 (최고 유사도 %.2f)",
            message[:30], len(similar), similar[0]["similarity"],
        )
    else:
        logger.debug("_enrich_issue: '%s' → 유사 사례 없음", message[:30])

    return {**issue, "similar_issues": similar}


# ── LangGraph 노드 ─────────────────────────────────────────────────────────────

async def vector_search_node(state: Dev2State) -> dict:
    """
    LangGraph 노드: CLI 도구 원본 이슈에 pgVector 유사 이슈를 주입한다.

    흐름:
        1. static_raw + security_raw → raw_issues 합산
        2. asyncpg 연결 풀 생성 (POSTGRES_URL 있을 때만)
        3. asyncio.gather로 이슈별 병렬 enrichment
        4. {"enriched": [...]} 반환 — LangGraph가 state에 merge

    CLAUDE.md §12:
        - 이슈가 없으면 빈 리스트 반환 (예외 없음)
        - DB 연결 실패 → Mock 검색으로 fallback (파이프라인 중단 없음)
        - 개별 이슈 실패 → similar_issues=[] 로 처리 (나머지 계속)

    Args:
        state: Dev2State — static_raw, security_raw, skill_level 필드 사용

    Returns:
        {"enriched": [...]} — similar_issues가 주입된 이슈 목록
    """
    static_raw = state.get("static_raw", [])
    security_raw = state.get("security_raw", [])

    # _source 태깅: store 노드가 에이전트별 분리에 사용 (Task 4-f)
    # 각 이슈에 원본 에이전트 정보를 보존 → store_node._source 기준 분리
    raw_issues = (
        [{**issue, "_source": "static"} for issue in static_raw]
        + [{**issue, "_source": "security"} for issue in security_raw]
    )

    if not raw_issues:
        logger.warning("vector_search_node: 분석 이슈 없음 — enriched 생략")
        return {"enriched": []}

    use_mock = os.getenv("USE_MOCK_LLM", "true").lower() == "true"
    logger.info(
        "vector_search_node: 이슈 %d개 enrichment 시작 (mock=%s)",
        len(raw_issues), use_mock,
    )

    # DB 풀 생성 (Mock 모드거나 POSTGRES_URL 없으면 None → Mock 검색으로 fallback)
    pool: asyncpg.Pool | None = None
    if not use_mock:
        pool = await _get_pool()

    try:
        # 이슈별 병렬 enrichment (asyncio.gather + return_exceptions)
        tasks = [_enrich_issue(issue, use_mock, pool) for issue in raw_issues]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        enriched: list[dict] = []
        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                # 개별 실패 → similar_issues=[] 로 원본 유지 (CLAUDE.md §12)
                logger.error(
                    "vector_search_node: 이슈 %d enrichment 예외 — %s | similar_issues=[]",
                    idx, result,
                )
                enriched.append({**raw_issues[idx], "similar_issues": []})
            else:
                enriched.append(result)

    finally:
        # 연결 풀 반납 (생성했을 때만)
        if pool is not None:
            await pool.close()

    found_count = sum(1 for e in enriched if e.get("similar_issues"))
    logger.info(
        "vector_search_node 완료: 총 %d개 이슈, 유사 사례 있음 %d개",
        len(enriched), found_count,
    )

    return {"enriched": enriched}
