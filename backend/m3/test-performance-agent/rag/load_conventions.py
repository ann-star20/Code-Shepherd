"""사내 컨벤션 문서 적재 (B안 ③ 저장) — 문서 → 청크 → embed → INSERT.

1회·사전 실행. 절대규칙(위험 1): 임베딩은 공유 rag.embedder.embed 사용
(저장과 검색이 같은 모델). 차원·테이블은 rag.store에 집중(위험 2).

외부 의존(모델·DB)은 인자 주입으로 테스트에서 고립한다.
실제 실행은 __main__에서 conventions/ 폴더의 .md를 읽어 적재.
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


def _chunk(content: str) -> list[str]:
    """빈 줄(문단) 기준 청크 분리. 공백/빈 청크 제외."""
    return [c.strip() for c in content.split("\n\n") if c.strip()]


def _doc_title(content: str, fallback: str) -> str:
    """첫 H1(`# ...`)을 문서 제목으로. 없으면 fallback(파일명)."""
    for line in content.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def load_from_dir(dir_path: str, conn, embed=None) -> int:
    """conventions/*.md 를 읽어 records로 만든 뒤 embed_and_store 호출.

    doc_title = 첫 H1(없으면 파일명 stem), source_url = ''(사내 링크 생기면 채움).
    .md 외 파일은 무시. 반환: INSERT한 청크 행 수.
    """
    records: list[dict] = []
    policies: list[tuple[str, str, dict]] = []
    for md in sorted(Path(dir_path).glob("*.md")):
        raw = md.read_text(encoding="utf-8")
        meta, body = _split_frontmatter(raw)
        # 프론트매터(숫자 정책) → 정책표용으로 수집
        if meta and meta.get("policy_key"):
            policies.append((
                str(meta["policy_key"]),
                str(meta.get("rule_id", "")),
                meta.get("params") or {},
            ))
        # 산문 본문만 임베딩 (프론트매터 제외)
        records.append({
            "doc_title": _doc_title(body, md.stem),
            "source_url": "",
            "content": body,
        })

    # 정책 UPSERT (있는 문서만). 같은 conn·트랜잭션에서 임베딩과 함께 처리.
    if policies:
        from config import policy_store  # noqa: PLC0415

        policy_store.ensure_table(conn)
        for key, rule_id, params in policies:
            policy_store.upsert_policy(conn, key, rule_id, params)

    return embed_and_store(records, conn, embed)


def embed_and_store(records: list[dict], conn, embed=None) -> int:
    """records=[{doc_title, source_url, content}] → 청크별 임베딩 후 INSERT.

    embed 미주입 시 공유 embedder.embed 사용(절대규칙). 반환: INSERT한 행 수.
    """
    if embed is None:
        embed = embedder.embed

    store.ensure_convention_table(conn)

    rows: list[tuple[str, str, str]] = []
    for r in records:
        for chunk in _chunk(r.get("content", "")):
            rows.append((r["doc_title"], r.get("source_url", ""), chunk))

    if not rows:
        return 0

    vectors = embed([text for _, _, text in rows])
    with conn.cursor() as cur:
        for (title, url, text), vec in zip(rows, vectors):
            cur.execute(
                "INSERT INTO convention_embeddings "
                "(doc_title, source_url, content, embedding) "
                "VALUES (%s, %s, %s, %s::vector)",
                (title, url, text, store.to_vector_literal(vec)),
            )
    return len(rows)


def load_conventions_to_chunks(dir_path: str, conn, embed=None) -> int:
    """A1 fix: 각 .md 가이드 → documents(1) + parent chunk(1) + child chunks(N) + embeddings(N).

    기존 embed_and_store(→convention_embeddings)와 독립. retriever가 사용하는
    chunks/chunk_embeddings/documents 테이블에 직접 적재.

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
    # 실제 적재 — conventions/*.md → BGE-M3 임베딩 → convention_embeddings.
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
