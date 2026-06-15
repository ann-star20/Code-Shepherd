"""chunk_embeddings 에서 우리가 삽입한 corpus 행 삭제.

실행 조건: ENABLE_DB_WRITE=true
대상: metadata->>'storage_path' LIKE 'corpus/%'
연계 삭제: CASCADE로 chunks, documents도 자동 삭제됨.

사용법:
  python -m scripts.cleanup_corpus_chunks
  python -m scripts.cleanup_corpus_chunks --dry-run
"""
from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv()

import os
import psycopg2


def _get_conn():
    host = os.getenv("DB_HOST", "")
    if not host:
        raise RuntimeError("DB_HOST 미설정")
    return psycopg2.connect(
        host=host,
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", ""),
        user=os.getenv("DB_USER", ""),
        password=os.getenv("DB_PASSWORD", ""),
        sslmode="require",
        connect_timeout=15,
    )


def main(dry_run: bool = False) -> None:
    enable_write = os.getenv("ENABLE_DB_WRITE", "false").lower() == "true"
    if not dry_run and not enable_write:
        print("[abort] ENABLE_DB_WRITE=true 가 아닌 상태에서는 실행 불가.")
        sys.exit(1)

    conn = _get_conn()
    cur = conn.cursor()

    # 삭제 대상 확인
    cur.execute("""
        SELECT metadata->>'storage_path', COUNT(*) as cnt
        FROM chunk_embeddings
        WHERE metadata->>'storage_path' LIKE 'corpus/%%'
        GROUP BY 1 ORDER BY 1
    """)
    targets = cur.fetchall()
    total = sum(r[1] for r in targets)

    print(f"[cleanup] corpus/* 삭제 대상: {total}행")
    for path, cnt in targets:
        print(f"  {path}: {cnt}행")

    if total == 0:
        print("[cleanup] 삭제할 corpus 행 없음. 완료.")
        conn.close()
        return

    if dry_run:
        print("\n[dry-run] 실제 삭제 없음.")
        conn.close()
        return

    # chunk_embeddings 삭제 (chunks/documents는 CASCADE로 자동 삭제됨)
    cur.execute("""
        DELETE FROM chunk_embeddings
        WHERE metadata->>'storage_path' LIKE 'corpus/%%'
    """)
    deleted_emb = cur.rowcount
    print(f"\n[cleanup] chunk_embeddings 삭제: {deleted_emb}행")

    # chunks 삭제 (doc_id로 연결된 것, chunk_id FK는 CASCADE 이미 처리됨)
    cur.execute("""
        DELETE FROM chunks
        WHERE doc_id IN (
            SELECT doc_id FROM documents
            WHERE file_path LIKE 'corpus/%%'
        )
    """)
    deleted_chunks = cur.rowcount
    print(f"[cleanup] chunks 삭제: {deleted_chunks}행")

    # documents 삭제
    cur.execute("""
        DELETE FROM documents
        WHERE file_path LIKE 'corpus/%%'
    """)
    deleted_docs = cur.rowcount
    print(f"[cleanup] documents 삭제: {deleted_docs}행")

    conn.commit()
    cur.close()
    conn.close()

    print("\n[cleanup] 완료. 잔여 corpus 행 확인:")
    _verify()


def _verify() -> None:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT metadata->>'category', COUNT(*) as cnt
        FROM chunk_embeddings
        WHERE metadata->>'category' IN ('보안', '코드성능검증', '코딩컨벤션')
        GROUP BY 1 ORDER BY cnt DESC
    """)
    print("  category | count")
    for cat, cnt in cur.fetchall():
        print(f"  {cat}: {cnt}")
    cur.execute("""
        SELECT COUNT(*) FROM chunk_embeddings
        WHERE metadata->>'storage_path' LIKE 'corpus/%%'
    """)
    corpus_left = cur.fetchone()[0]
    print(f"  corpus/* 잔여: {corpus_left}행")
    conn.close()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    main(dry_run=dry_run)
