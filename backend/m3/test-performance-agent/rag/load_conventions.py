"""사내 컨벤션 문서 재청킹 적재 (9A) — 가이드별 documents/chunks/chunk_embeddings.

※ 적재의 정본은 KMS(m0) 파이프라인이다. 이 모듈의 직접 적재(__main__)는
   사용자 승인 없이 실행하지 않는다. (옛 목업 convention_embeddings 적재
   함수는 제거됨 — 인용은 KMS 테이블에서만 나온다.)

절대규칙(위험 1): 임베딩은 공유 rag.embedder.embed 사용(저장과 검색이 같은 모델).
외부 의존(모델·DB)은 인자 주입으로 테스트에서 고립한다.
"""
from __future__ import annotations

from pathlib import Path

from rag import embedder, store


def _split_frontmatter(content: str) -> tuple[dict | None, str]:
    """문서 맨 위 YAML 프론트매터(--- ... ---)를 분리. (meta dict|None, 본문).

    프론트매터(숫자 정책)는 코드가 YAML로 정확히 읽고(위험3), 본문(산문)만
    임베딩되도록 떼어낸다. 프론트매터 없으면 (None, 원문 그대로).
    """
    if not content.startswith("---"):
        return None, content
    lines = content.splitlines()
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return None, content
    import yaml  # noqa: PLC0415

    try:
        meta = yaml.safe_load("\n".join(lines[1:end]))
    except Exception:
        return None, content
    if not isinstance(meta, dict):
        return None, content
    body = "\n".join(lines[end + 1:]).lstrip("\n")
    return meta, body


def _doc_title(content: str, fallback: str) -> str:
    """첫 H1(`# ...`)을 문서 제목으로. 없으면 fallback(파일명)."""
    for line in content.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def load_conventions_to_chunks(dir_path: str, conn, embed=None) -> int:
    """A1 fix: 각 .md 가이드 → documents(1) + parent chunk(1) + child chunks(N) + embeddings(N).

    retriever가 사용하는 chunks/chunk_embeddings/documents 테이블에 직접 적재.

    - section_header = 프론트매터 rule_id (없으면 doc_title) → 인용 라벨 정합성 수정.
    - source_url = 'file:///conventions/{파일명}' (식별·재적재 전용, A2 전 placeholder).
    - parent chunk은 가이드 전문(임베딩 없음), child chunk은 문단별 임베딩.

    반환: 삽입된 child chunk(=임베딩 행) 수.
    """
    if embed is None:
        embed = embedder.embed

    total = 0
    for md_path in sorted(Path(dir_path).glob("*.md")):
        raw = md_path.read_text(encoding="utf-8")
        meta, body = _split_frontmatter(raw)

        rule_id: str = (meta.get("rule_id") or "") if meta else ""
        doc_title: str = _doc_title(body, md_path.stem)
        section_hdr: str = rule_id or doc_title
        source_url: str = f"file:///conventions/{md_path.name}"

        # 1) documents
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO documents (title, source_url) VALUES (%s, %s) RETURNING doc_id",
                (doc_title, source_url),
            )
            (doc_id,) = cur.fetchone()

        # 2) parent chunk (전문, 임베딩 없음 — 검색은 child가 처리)
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO chunks (doc_id, content, section_header, parent_chunk_id) "
                "VALUES (%s, %s, %s, %s) RETURNING chunk_id",
                (doc_id, body, section_hdr, None),
            )
            (parent_id,) = cur.fetchone()

        # 3) child chunks (문단 분리) + embeddings
        children = [c.strip() for c in body.split("\n\n") if c.strip()]
        if not children:
            continue
        vectors = embed(children)
        for text, vec in zip(children, vectors):
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO chunks (doc_id, content, section_header, parent_chunk_id) "
                    "VALUES (%s, %s, %s, %s) RETURNING chunk_id",
                    (doc_id, text, section_hdr, parent_id),
                )
                (child_id,) = cur.fetchone()
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO chunk_embeddings (chunk_id, embedding) VALUES (%s, %s::vector)",
                    (child_id, store.to_vector_literal(vec)),
                )
            total += 1

    return total


if __name__ == "__main__":
    # 재청킹 적재 — conventions/*.md → BGE-M3 임베딩 → chunks/chunk_embeddings.
    # ※ 적재 정본은 KMS(m0) — 이 직접 적재는 사용자 승인 없이 실행 금지.
    # 전체 새로고침(DELETE 후 재적재)이라 재실행 안전. 성공 시에만 커밋.
    import os
    import sys

    _HERE = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(_HERE))  # test-performance-agent
    import persist  # noqa: E402
    import psycopg2  # noqa: E402

    conv_dir = os.path.join(os.path.dirname(_HERE), "conventions")
    url = persist._pg_url()
    if not url:
        print("POSTGRES_URL 없음 — 적재 불가")
        raise SystemExit(1)

    print(f"컨벤션 재청킹 적재 시작: {conv_dir}")
    print("(첫 실행이면 BGE-M3 ~2GB 다운로드 — 수 분 걸릴 수 있음)")
    conn = psycopg2.connect(url, connect_timeout=20)
    try:
        # 기존 convention 항목 삭제 (source_url 패턴으로 식별)
        _PREFIX = "file:///conventions/%"
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM chunk_embeddings WHERE chunk_id IN ("
                "  SELECT c.chunk_id FROM chunks c"
                "  JOIN documents d ON d.doc_id = c.doc_id"
                "  WHERE d.source_url LIKE %s)",
                (_PREFIX,),
            )
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM chunks WHERE doc_id IN ("
                "  SELECT doc_id FROM documents WHERE source_url LIKE %s)",
                (_PREFIX,),
            )
        with conn.cursor() as cur:
            cur.execute("DELETE FROM documents WHERE source_url LIKE %s", (_PREFIX,))

        n = load_conventions_to_chunks(conv_dir, conn)  # 공유 embedder(BGE-M3)
        conn.commit()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM chunk_embeddings ce"
                " JOIN chunks c ON c.chunk_id = ce.chunk_id"
                " JOIN documents d ON d.doc_id = c.doc_id"
                " WHERE d.source_url LIKE %s",
                (_PREFIX,),
            )
            total = cur.fetchone()[0]
        print(f"재청킹 적재 완료: {n}개 child chunk INSERT, 현재 총 {total}행")
    except Exception as e:
        conn.rollback()
        print("적재 실패(롤백):", type(e).__name__, "|", str(e)[:140])
        raise SystemExit(1)
    finally:
        conn.close()
