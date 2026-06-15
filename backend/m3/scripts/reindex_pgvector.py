"""corpus/*.md → documents → chunks → chunk_embeddings UPSERT (pgVector 재인덱싱)

실행 조건: ENABLE_DB_WRITE=true 일 때만 실제 쓰기 수행.
기존 m0 데이터는 건드리지 않음 — UPSERT (ON CONFLICT DO UPDATE).
결정적 UUID5 사용 — 반복 실행해도 중복 없음.

사용법:
  python -m scripts.reindex_pgvector            # 전체 재인덱싱
  python -m scripts.reindex_pgvector --dry-run  # DB 쓰기 없이 결과만 출력
"""
from __future__ import annotations

import json
import re
import sys
import uuid
from pathlib import Path
from typing import NamedTuple

from dotenv import load_dotenv

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE.parent))

load_dotenv()

import os

from src.embeddings import embed_texts

# ── 설정 ─────────────────────────────────────────────────────────────────────

CORPUS_DIR = _HERE.parent / "corpus"

RULE_CATEGORY: dict[str, str] = {
    "sql_binding":     "보안",
    "clickjacking":    "보안",
    "db_query":        "코드성능검증",
    "time_complexity": "코드성능검증",
    "external_api":    "코드성능검증",
    "error_handling":  "코드성능검증",
    "logging":         "코드성능검증",
    "config_env":      "코드성능검증",
    "js_deps":         "보안",
    "time_handling":   "코드성능검증",
}

_NS = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
EMBEDDING_MODEL = "bge-m3"


# ── 청크 파싱 ─────────────────────────────────────────────────────────────────

class _Chunk(NamedTuple):
    rule_id: str
    section: str
    text: str
    severity: str
    source_path: str
    stem: str


def _parse_corpus_file(path: Path) -> list[_Chunk]:
    raw = path.read_text(encoding="utf-8")
    stem = path.stem

    first_line = raw.split("\n")[0]
    id_match = re.search(r"\[([A-Z]+-[A-Z]+-\d+)\]", first_line)
    if not id_match:
        print(f"[skip] rule_id 없음: {path.name}")
        return []
    rule_id = id_match.group(1)

    sev_match = re.search(r"-\s*severity:\s*(Major|Minor|Info)", raw)
    severity = sev_match.group(1) if sev_match else "Info"
    source_path = f"corpus/{path.name}"
    parts = re.split(r"(?=^## §)", raw, flags=re.MULTILINE)

    chunks: list[_Chunk] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        sec_match = re.match(r"## (§\d+)", part)
        section = sec_match.group(1) if sec_match else "§0"
        chunks.append(_Chunk(
            rule_id=rule_id, section=section, text=part,
            severity=severity, source_path=source_path, stem=stem,
        ))
    return chunks


# ── UUID 헬퍼 ─────────────────────────────────────────────────────────────────

def _doc_id(stem: str) -> str:
    return str(uuid.uuid5(_NS, f"m3-doc-{stem}"))

def _chunk_id(stem: str, section: str) -> str:
    return str(uuid.uuid5(_NS, f"m3-chunk-{stem}-{section}"))


# ── DB 연결 ───────────────────────────────────────────────────────────────────

def _get_conn():
    import psycopg2
    from pgvector.psycopg2 import register_vector

    host = os.getenv("DB_HOST", "")
    if not host:
        raise RuntimeError("DB_HOST 미설정")
    conn = psycopg2.connect(
        host=host,
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", ""),
        user=os.getenv("DB_USER", ""),
        password=os.getenv("DB_PASSWORD", ""),
        sslmode="require",
        connect_timeout=15,
    )
    register_vector(conn)
    return conn


# ── SQL ───────────────────────────────────────────────────────────────────────

_DOC_UPSERT = """
INSERT INTO documents (
    doc_id, title, source, file_type, category,
    file_path, storage_synced, neo4j_synced,
    upload_status, permission_level, visibility,
    created_at, updated_at
)
VALUES (%s, %s, 'upload', 'md', %s, %s, false, false,
        'stored', 'public', 'all',
        NOW(), NOW())
ON CONFLICT (doc_id) DO UPDATE SET
    title      = EXCLUDED.title,
    category   = EXCLUDED.category,
    file_path  = EXCLUDED.file_path,
    updated_at = NOW()
"""

_CHUNK_UPSERT = """
INSERT INTO chunks (
    chunk_id, doc_id, chunk_type, content,
    token_count, section_header, storage_path,
    permission_level, created_at
)
VALUES (%s, %s, 'child', %s, %s, %s, %s, 'public', NOW())
ON CONFLICT (chunk_id) DO UPDATE SET
    content        = EXCLUDED.content,
    token_count    = EXCLUDED.token_count,
    section_header = EXCLUDED.section_header,
    storage_path   = EXCLUDED.storage_path
"""

_EMB_UPSERT = """
INSERT INTO chunk_embeddings (chunk_id, embedding, model_name, content, metadata, created_at)
VALUES (%s, %s::vector, %s, %s, %s::jsonb, NOW())
ON CONFLICT (chunk_id) DO UPDATE SET
    embedding   = EXCLUDED.embedding,
    model_name  = EXCLUDED.model_name,
    content     = EXCLUDED.content,
    metadata    = EXCLUDED.metadata
"""


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main(dry_run: bool = False) -> None:
    enable_write = os.getenv("ENABLE_DB_WRITE", "false").lower() == "true"
    if not dry_run and not enable_write:
        print("[abort] ENABLE_DB_WRITE=true 가 아닌 상태에서는 실행 불가.")
        sys.exit(1)

    md_files = sorted(f for f in CORPUS_DIR.glob("*.md") if f.name != "README.md")
    if not md_files:
        print(f"[abort] corpus 파일 없음: {CORPUS_DIR.resolve()}")
        sys.exit(1)

    print(f"[reindex] corpus 파일 {len(md_files)}개 파싱...")
    all_chunks: list[_Chunk] = []
    for f in md_files:
        chunks = _parse_corpus_file(f)
        print(f"  {f.name}: {len(chunks)}개 청크")
        all_chunks.extend(chunks)

    print(f"\n[reindex] 총 {len(all_chunks)}개 청크 임베딩 시작 (bge-m3)...")
    vectors = embed_texts([c.text for c in all_chunks])
    print(f"[reindex] 임베딩 완료 — 벡터 {len(vectors)}개, 차원 {len(vectors[0])}")

    if dry_run:
        print("\n[dry-run] DB 쓰기 없음. 파싱 결과:")
        for c in all_chunks:
            cid = _chunk_id(c.stem, c.section)
            cat = RULE_CATEGORY.get(c.stem, "코드성능검증")
            print(f"  {cid[:8]}… | {c.rule_id} | {c.section} | {cat} | {len(c.text)}자")
        return

    conn = _get_conn()
    cur = conn.cursor()

    # ① documents UPSERT (파일당 1행)
    stems_done: set[str] = set()
    for chunk in all_chunks:
        if chunk.stem in stems_done:
            continue
        stems_done.add(chunk.stem)
        cat = RULE_CATEGORY.get(chunk.stem, "코드성능검증")
        did = _doc_id(chunk.stem)
        cur.execute(_DOC_UPSERT, (
            did,
            f"M3 코드리뷰 규칙: {chunk.rule_id}",
            cat,
            chunk.source_path,
        ))
    print(f"\n[reindex] documents UPSERT — {len(stems_done)}행")

    # ② chunks UPSERT
    for chunk in all_chunks:
        cid  = _chunk_id(chunk.stem, chunk.section)
        did  = _doc_id(chunk.stem)
        tok  = max(1, len(chunk.text.split()))
        cur.execute(_CHUNK_UPSERT, (
            cid, did, chunk.text, tok,
            chunk.section, chunk.source_path,
        ))
    print(f"[reindex] chunks UPSERT — {len(all_chunks)}행")

    # ③ chunk_embeddings UPSERT
    for chunk, vec in zip(all_chunks, vectors):
        cid  = _chunk_id(chunk.stem, chunk.section)
        cat  = RULE_CATEGORY.get(chunk.stem, "코드성능검증")
        meta = json.dumps({
            "category":        cat,
            "storage_path":    chunk.source_path,
            "section_header":  chunk.section,
            "rule_id":         chunk.rule_id,
            "severity":        chunk.severity,
            "embedding_model": EMBEDDING_MODEL,
        }, ensure_ascii=False)
        cur.execute(_EMB_UPSERT, (cid, vec, EMBEDDING_MODEL, chunk.text, meta))
    print(f"[reindex] chunk_embeddings UPSERT — {len(all_chunks)}행")

    conn.commit()
    cur.close()
    conn.close()

    print("\n[reindex] 완료. ENABLE_DB_WRITE=false 로 복구하세요.")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    main(dry_run=dry_run)
