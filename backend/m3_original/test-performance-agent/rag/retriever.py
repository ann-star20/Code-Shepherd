"""사내 컨벤션 검색 (B안 ① 검색) — 쿼리 embed + pgvector 코사인 검색.

A안(Dev1 KMS API 위임) 폐기. Dev3가 직접:
  이슈 message(위험 4) → 공유 embedder.embed(위험 1) → pgvector 코사인 → top-k.

시그니처·반환형은 A안과 동일 → augment·llm_refiner·R8 무수정.
환각 방지(위험·정직, 설계서 §4.3):
  - DB 연결 없음(POSTGRES_URL 미설정) / 모델 실패 / 예외 → 빈 리스트
  - score(=1-코사인거리) < RAG_SCORE_MIN 결과 제거
"""
from __future__ import annotations

import persist
from config import settings
from rag import embedder, store

_SEARCH_SQL = (
    "SELECT content, doc_title, source_url, "
    "1 - (embedding <=> %s::vector) AS score "
    "FROM convention_embeddings "
    "ORDER BY embedding <=> %s::vector LIMIT %s"
)


def _connect():
    """GCP Postgres 연결(POSTGRES_URL). 없으면 None. 테스트에서 monkeypatch 대상."""
    url = persist._pg_url()
    if not url:
        return None
    import psycopg2  # noqa: PLC0415

    return psycopg2.connect(url, connect_timeout=10)


def search_convention(query_text: str, top_k: int = 3) -> list[dict]:
    """이슈 message 통째로(위험 4) → BGE-M3 임베딩 → pgvector 코사인 검색.

    반환: [{content, doc_title, source_url, score}, ...] (없으면 빈 리스트).
    """
    conn = None
    try:
        conn = _connect()
        if conn is None:
            return []  # DB 미설정 → 표준 fallback (환각 방지)
        vec = embedder.embed([query_text])  # 저장과 동일 임베더(위험 1)
        if not vec:
            return []
        qlit = store.to_vector_literal(vec[0])
        with conn.cursor() as cur:
            cur.execute(_SEARCH_SQL, (qlit, qlit, top_k))
            rows = cur.fetchall()
    except Exception:
        return []  # 모델/DB 실패 → 빈 결과 (가짜 문서 지어내지 않음)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    results = [
        {"content": c, "doc_title": t, "source_url": u, "score": float(s)}
        for (c, t, u, s) in rows
    ]
    return [r for r in results if r["score"] >= settings.RAG_SCORE_MIN]
