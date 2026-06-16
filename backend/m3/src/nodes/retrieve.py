"""② retrieve — queries → chunks (pgVector KMS 검색 또는 ChromaDB 로컬 검색)

USE_PGVECTOR=true  → m0 chunk_embeddings pgVector 유사도 검색
USE_PGVECTOR=false → ChromaDB 로컬 컬렉션 검색 (기본값 / eval 안전 경로)

계약: contracts/README.md 표 ②
임베딩: src/embeddings.embed_texts — 인덱스와 질의가 반드시 같은 provider/model.
"""
from __future__ import annotations

import logging
import os
import re

from dotenv import load_dotenv

from contracts import Chunk, ReviewState
from src.config import MAX_JUDGE_CHUNKS, TOP_K
from src.embeddings import embed_texts

load_dotenv()
log = logging.getLogger(__name__)

# ── pgVector 경로 설정 ────────────────────────────────────────────────────────

_KMS_CATEGORIES = ["보안", "코드성능검증", "코딩컨벤션"]

_PATH_RULE_MAP: dict[str, tuple[str, str]] = {
    "sql_binding":     ("CONV-SQL-008",  "Major"),
    "clickjacking":    ("CONV-SEC-010",  "Major"),
    "config_env":      ("CONV-CFG-007",  "Minor"),
    "db_query":        ("CONV-DB-004",   "Major"),
    "error_handling":  ("CONV-ERR-006",  "Minor"),
    "external_api":    ("CONV-API-001",  "Major"),
    "js_deps":         ("CONV-DEP-005",  "Major"),
    "logging":         ("CONV-LOG-003",  "Minor"),
    "time_complexity": ("CONV-PERF-009", "Minor"),
    "time_handling":   ("CONV-TIME-002", "Minor"),
    "memory_leak":     ("CONV-MEM-011",  "Major"),
}

_RULE_SEVERITY: dict[str, str] = {r: s for r, s in _PATH_RULE_MAP.values()}
_RULE_ID_RE = re.compile(r"CONV-[A-Z]+-\d+")

# 키워드 기반 rule_id 추론 — m0 데이터는 storage_path/rule_id 없이 내용만 있음
_KMS_KEYWORD_MAP: list[tuple[list[str], str, str]] = [
    (["SQL Injection", "Parameterized Query", "sql injection", "f-string SQL", "바인딩", "인젝션", "safe_query"],
     "CONV-SQL-008", "Major"),
    (["N+1", "N+1 query", "루프 안에", "쿼리 발생", "select_related", "prefetch_related", "bulk_fetch"],
     "CONV-DB-004", "Major"),
    (["X-Frame", "clickjacking", "클릭재킹", "XFrameOptions"],
     "CONV-SEC-010", "Major"),
    (["requests.get", "requests.post", "동기 HTTP", "블로킹", "event loop", "asyncio", "urllib"],
     "CONV-API-001", "Major"),
    (["datetime.now", "utcnow", "타임존", "timezone", "UTC", "aware", "astimezone"],
     "CONV-TIME-002", "Minor"),
    (["print(", "f-string 로그", "구조적 로깅", "structured log", "struct_logger"],
     "CONV-LOG-003", "Minor"),
    (["except:", "except Exception", "pass", "무음", "silent exception", "삼킴"],
     "CONV-ERR-006", "Minor"),
    (["os.getenv", "os.environ", "환경변수 직접", "config.from_env"],
     "CONV-CFG-007", "Minor"),
    (["lodash", "의존성 금지", "금지 라이브러리", "ts-stdlib"],
     "CONV-DEP-005", "Major"),
    (["O(N²)", "시간복잡도", "sorted()", "set 변환", "time complexity"],
     "CONV-PERF-009", "Minor"),
    (["Memory Leak", "메모리 누수", "Unbounded Collection", "무한히 커지는",
      "캐시 무한 증가", "Python GC", "자료구조 증가", "CONV-MEM-011",
      "unbounded", "maxsize 없음", "TTL 없음"],
     "CONV-MEM-011", "Major"),
]


def _infer_rule(content: str, section_header: str, storage_path: str) -> tuple[str, str]:
    """content / section_header / storage_path 에서 rule_id 와 severity 를 추론한다."""
    combined = (content or "") + " " + (section_header or "")
    # 1) 정규식으로 직접 추출 (코퍼스 헤더 포함 청크)
    m = _RULE_ID_RE.search(combined)
    if m:
        rule_id = m.group()
        return rule_id, _RULE_SEVERITY.get(rule_id, "Minor")
    # 2) storage_path 파일명 stem 매핑
    if storage_path:
        stem = storage_path.replace("\\", "/").split("/")[-1].replace(".md", "")
        if stem in _PATH_RULE_MAP:
            return _PATH_RULE_MAP[stem]
    # 3) 키워드 매핑 (m0 교육 콘텐츠 형식)
    for keywords, rule_id, severity in _KMS_KEYWORD_MAP:
        for kw in keywords:
            if kw in combined:
                return rule_id, severity
    return "CONV-UNKNOWN-000", "Minor"


def _embed(text: str) -> list[float]:
    return embed_texts([text])[0]


# ── pgVector 검색 ─────────────────────────────────────────────────────────────

def _retrieve_pgvector(queries: list[str]) -> list[Chunk]:
    import psycopg2
    from pgvector.psycopg2 import register_vector

    host = os.getenv("DB_HOST", "")
    if host:
        conn = psycopg2.connect(
            host=host,
            port=int(os.getenv("DB_PORT", "5432")),
            dbname=os.getenv("DB_NAME", ""),
            user=os.getenv("DB_USER", ""),
            password=os.getenv("DB_PASSWORD", ""),
            sslmode="require",
            connect_timeout=10,
        )
    else:
        url = os.getenv("POSTGRES_URL", "")
        if not url:
            raise RuntimeError("DB_HOST 또는 POSTGRES_URL 환경변수 없음")
        conn = psycopg2.connect(dsn=url, connect_timeout=10)

    register_vector(conn)
    cur = conn.cursor()
    seen_ids: set[str] = set()
    chunks: list[Chunk] = []

    for query in queries:
        if len(chunks) >= MAX_JUDGE_CHUNKS:
            break
        vec = _embed(query)
        cur.execute(
            """
            SELECT content,
                   metadata->>'section_header' AS section,
                   metadata->>'storage_path'   AS path,
                   1 - (embedding <=> %s::vector) AS score
            FROM chunk_embeddings
            WHERE metadata->>'category' = ANY(%s)
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (vec, _KMS_CATEGORIES, vec, TOP_K),
        )
        for content, section, path, score in cur.fetchall():
            rule_id, severity = _infer_rule(content or "", section or "", path or "")
            chunk_id = f"{rule_id}_{section or path or content[:20]}"
            if chunk_id in seen_ids:
                continue
            seen_ids.add(chunk_id)
            chunks.append(Chunk(
                rule_id=rule_id,
                section=section or "",
                text=content or "",
                severity=severity,
                score=float(score or 0.0),
                source_path=path or "",
            ))

    cur.close()
    conn.close()
    return chunks[:MAX_JUDGE_CHUNKS]


# ── ChromaDB 검색 (로컬 백업 / eval 기본 경로) ────────────────────────────────

def _retrieve_chroma(queries: list[str]) -> list[Chunk]:
    import chromadb
    from src.config import CHROMA_COLLECTION, CHROMA_DIR
    from src.embeddings import _active_model

    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_collection(CHROMA_COLLECTION)
    idx_model = (collection.metadata or {}).get("embedding_model")
    if idx_model and idx_model != _active_model():
        raise RuntimeError(
            f"인덱스/질의 임베딩 불일치: 인덱스={idx_model}, 현재={_active_model()}"
        )

    seen_ids: set[str] = set()
    chunks: list[Chunk] = []

    for query in queries:
        if len(chunks) >= MAX_JUDGE_CHUNKS:
            break
        vec = _embed(query)
        results = collection.query(
            query_embeddings=[vec],
            n_results=min(TOP_K, collection.count()),
            include=["documents", "metadatas", "distances"],
        )
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            chunk_id = f"{meta['rule_id']}_{meta['section']}"
            if chunk_id in seen_ids:
                continue
            seen_ids.add(chunk_id)
            chunks.append(Chunk(
                rule_id=meta["rule_id"],
                section=meta["section"],
                text=doc,
                severity=meta["severity"],
                score=float(1.0 - dist),
                source_path=meta["source_path"],
            ))

    return chunks[:MAX_JUDGE_CHUNKS]


# ── 공개 노드 함수 ────────────────────────────────────────────────────────────

def retrieve(state: ReviewState) -> dict:
    queries: list[str] = state.get("queries", [])
    if not queries:
        return {"chunks": []}

    use_pgvector = os.getenv("USE_PGVECTOR", "false").lower() == "true"

    if use_pgvector:
        try:
            chunks = _retrieve_pgvector(queries)
            log.info("retrieve: pgVector %d chunks 반환", len(chunks))
            return {"chunks": chunks}
        except Exception as exc:
            log.warning("retrieve: pgVector 실패, ChromaDB 폴백 — %s", exc)

    try:
        chunks = _retrieve_chroma(queries)
        log.info("retrieve: ChromaDB %d chunks 반환", len(chunks))
        return {"chunks": chunks}
    except Exception as exc:
        log.error("retrieve: ChromaDB도 실패 — %s", exc)
        return {"chunks": []}
