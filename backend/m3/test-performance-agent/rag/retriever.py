"""사내 컨벤션 검색 (7A) — 쿼리 embed + pgvector 코사인 검색 (small-to-big).

진짜 사내규칙은 chunks/chunk_embeddings 에 parent-child 로 들어있다:
  - chunk_embeddings(=정밀 매칭용 child 임베딩) 를 코사인 검색해 가장 가까운 child 를 찾고,
  - 그 child 의 parent_chunk_id 로 부모(=검색용 큰 청크) 본문을 통째로 인용한다.
    (부모 없으면 child 본문으로 fallback.)
한 번의 쿼리로 child→부모→문서를 join 해 가져오고(=N+1 회피), 부모/child 선택·title
매핑·score 컷은 파이썬에서 한다.

시그니처·반환형은 그대로 유지 → augment·llm_refiner·R8 무수정:
  [{content, doc_title, source_url, score}, ...]
임베딩 모델은 chunks 쪽과 동일한 bge-m3(1024) → 공유 embedder.embed 그대로 사용(위험 1).

환각 방지(위험·정직, 설계서 §4.3):
  - DB 연결 없음(POSTGRES_URL 미설정) / 모델 실패 / 예외 → 빈 리스트(가짜 인용 금지)
  - source_url 없으면 빈 문자열(가짜 링크 금지)
  - score(=1-코사인거리) < RAG_SCORE_MIN 결과 제거
"""
from __future__ import annotations

import persist
from config import settings
from rag import embedder, store

# child 임베딩으로 정밀 매칭 → 부모 본문(small-to-big)·문서 메타를 한 쿼리로 join.
# 부모/문서는 LEFT JOIN (부모 없음·문서 메타 누락 시에도 child 로 동작).
_SEARCH_SQL = (
    "SELECT "
    "p.content AS parent_content, "
    "c.content AS child_content, "
    "p.section_header AS parent_section_header, "
    "c.section_header AS child_section_header, "
    "d.title AS doc_title, "
    "d.source_url AS source_url, "
    "1 - (ce.embedding <=> %s::vector) AS score "
    "FROM chunk_embeddings ce "
    "JOIN chunks c ON c.chunk_id = ce.chunk_id "
    "LEFT JOIN chunks p ON p.chunk_id = c.parent_chunk_id "
    "LEFT JOIN documents d ON d.doc_id = c.doc_id "
    "ORDER BY ce.embedding <=> %s::vector "
    "LIMIT %s"
)


def _connect():
    """GCP Postgres 연결(POSTGRES_URL). 없으면 None. 테스트에서 monkeypatch 대상."""
    url = persist._pg_url()
    if not url:
        return None
    import psycopg2  # noqa: PLC0415

    return psycopg2.connect(url, connect_timeout=10)


def search_convention(query_text: str, top_k: int = 3) -> list[dict]:
    """이슈 message 통째로(위험 4) → BGE-M3 임베딩 → child 코사인 검색 → 부모 본문 인용.

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

    results: list[dict] = []
    for (p_content, c_content, p_sh, c_sh, d_title, src_url, score) in rows:
        if p_content:  # small-to-big: 부모 본문을 인용
            content, section = p_content, p_sh
        else:  # 부모 없음(parent_chunk_id NULL) → child 본문 fallback
            content, section = c_content, c_sh
        results.append({
            "content": content,
            "doc_title": section or d_title or "",  # 섹션 헤더 → 문서 제목 순
            "source_url": src_url or "",  # 없으면 빈 문자열(가짜 링크 금지)
            "score": float(score),
        })
    return [r for r in results if r["score"] >= settings.RAG_SCORE_MIN]
