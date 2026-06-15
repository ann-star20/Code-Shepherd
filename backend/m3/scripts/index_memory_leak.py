"""ecommerce_memory_leak_fixed.docx → documents → chunks → chunk_embeddings UPSERT

CONV-MEM-011 (Unbounded Collection Growth) KMS 문서를 pgVector에 인덱싱한다.

실행 조건: ENABLE_DB_WRITE=true 일 때만 실제 쓰기 수행.
결정적 UUID5 사용 — 반복 실행해도 중복 없음.

사용법 (컨테이너 내부):
  python scripts/index_memory_leak.py          # 실제 쓰기
  python scripts/index_memory_leak.py --dry-run  # 쓰기 없이 검증만
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE.parent))

load_dotenv()

from src.embeddings import embed_texts  # noqa: E402

# ── 상수 ─────────────────────────────────────────────────────────────────────

_NS = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
EMBEDDING_MODEL = "bge-m3"
STORAGE_PATH = "kms_docs/memory_leak.md"
CATEGORY = "코딩컨벤션"
RULE_ID = "CONV-MEM-011"
SEVERITY = "Major"
DOC_STEM = "memory_leak"

# ── KMS 청크 내용 (docx에서 추출한 핵심 내용) ─────────────────────────────

CHUNKS: list[dict] = [
    {
        "section": "§0",
        "text": (
            "[CONV-MEM-011] Memory Leak: Unbounded Collection Growth — severity: Major\n\n"
            "무한히 커지는 자료구조 (Unbounded Collection Growth) Python 의미 가이드\n\n"
            "핵심 키워드: Memory Leak, Unbounded Collection Growth, Python GC, "
            "캐시 무한 증가, cache/queue/log buffer 증가, 메모리 누수\n\n"
            "규칙: CONV-MEM-011 — 자료구조에 크기를 제한하는 전략 없이 상태가 계속 "
            "append, insert, put, assign 되는 구조는 메모리 누수를 유발한다.\n\n"
            "E-commerce 엔진의 플랫폼 팀, 백엔드 엔지니어, 데이터 엔지니어에게 "
            "필수 가이드. maxsize, TTL, LRU, deque(maxlen), Queue(maxsize), "
            "pagination, streaming, batch 처리, 모니터링 필수."
        ),
    },
    {
        "section": "§1",
        "text": (
            "CONV-MEM-011 §1 — Unbounded Collection이란\n\n"
            "Unbounded Collection Growth란 자료구조의 크기를 제한하는 전략 없이 "
            "상태가 계속 append, insert, put, assign 되는 구조다. "
            "Python의 GC는 있어도, 참조가 남아있는 한 메모리를 회수하지 않는다.\n\n"
            "list: request log, product view history, temporary result에 계속 "
            "append하면서 clear하지 않음 → 요청마다 메모리 증가\n"
            "dict: user_id, session_id, product_id를 key로 계속 누적되며 "
            "TTL/삭제 전략이 없음 → 종료 없이 커지기만 함\n"
            "cache: maxsize, TTL, eviction policy 설정 없이 적재만 하는 딕셔너리 "
            "→ 캐시 무한 증가\n"
            "queue: 생산자는 계속 put하면서 소비자가 멈추거나 느리고, "
            "queue size 제한도 없음 → backlog 무제한 증가\n"
            "log buffer: 검색/클릭/추천 데이터를 메모리 버퍼에 무제한으로 "
            "flush 또는 rotate 없이 누적"
        ),
    },
    {
        "section": "§2",
        "text": (
            "CONV-MEM-011 §2 — 안티패턴 (BAD 코드)\n\n"
            "# BAD - 캐시가 무한히 커지는 패턴 (Unbounded dict cache)\n"
            "product_cache = {}  # maxsize 없음\n\n"
            "def get_product(product_id):\n"
            "    if product_id not in product_cache:\n"
            "        product_cache[product_id] = db.query(product_id)  # 무한 증가\n"
            "    return product_cache[product_id]\n\n"
            "# BAD - 로그 버퍼가 무한히 커지는 패턴\n"
            "search_logs = []  # clear 없음\n\n"
            "def log_search(query, user_id):\n"
            "    search_logs.append({'query': query, 'user_id': user_id, 'ts': time.time()})\n\n"
            "# BAD - 히스토리가 무한히 커지는 패턴\n"
            "product_view_history = defaultdict(list)  # maxsize 없음\n\n"
            "def record_view(user_id, product_id):\n"
            "    product_view_history[user_id].append(product_id)  # unbounded\n\n"
            "# BAD - 추천 결과를 메모리에 무제한 누적\n"
            "recommendation_cache = {}  # TTL 없음, eviction 없음\n\n"
            "위 패턴들은 CONV-MEM-011 위반: 서비스 장기 실행 시 OOM, "
            "컨테이너 재시작, HTTP 500/503 유발."
        ),
    },
    {
        "section": "§3",
        "text": (
            "CONV-MEM-011 §3 — 올바른 패턴 (bounded collection)\n\n"
            "# GOOD - LRU cache with maxsize\n"
            "from functools import lru_cache\n\n"
            "@lru_cache(maxsize=1000)\n"
            "def get_product(product_id):\n"
            "    return db.query(product_id)\n\n"
            "# GOOD - bounded deque for history\n"
            "from collections import deque\n"
            "product_view_history = defaultdict(lambda: deque(maxlen=100))\n\n"
            "def record_view(user_id, product_id):\n"
            "    product_view_history[user_id].append(product_id)  # 자동 제거\n\n"
            "# GOOD - bounded queue\n"
            "from queue import Queue\n"
            "event_queue = Queue(maxsize=10000)\n\n"
            "# GOOD - TTL cache with maxsize\n"
            "import cachetools\n"
            "session_cache = cachetools.TTLCache(maxsize=5000, ttl=3600)\n\n"
            "# GOOD - log buffer with periodic flush\n"
            "from collections import deque\n"
            "search_logs = deque(maxlen=10000)  # 최대 크기 제한\n\n"
            "수정 원칙: 모든 컬렉션에 maxsize/TTL/eviction 정책을 명시한다."
        ),
    },
    {
        "section": "§4",
        "text": (
            "CONV-MEM-011 §4 — E-commerce 시나리오별 체크리스트\n\n"
            "자료구조 | E-commerce 활용 | 해결 전략\n"
            "list | 상품 조회 로그, 임시 결과 저장 | deque(maxlen=N) 또는 paginate\n"
            "dict | 세션 캐시, 상품 캐시, 세율 데이터 | TTL + maxsize + logout/expire cleanup\n"
            "cache | 상품 및 API 응답, 추천 결과, 배너 설정 | functools.lru_cache(maxsize=N) 또는 외부 cache + TTL\n"
            "queue | 주문/배송/결제 이벤트 | Queue(maxsize=N) + consumer + retry/DLQ\n"
            "log buffer | 클릭/검색/추천 분석 데이터 | batch flush + external storage\n\n"
            "PR 작성 시 요구사항:\n"
            "- 해당 자료구조의 최대 크기 또는 최대 메모리 사용량\n"
            "- 데이터를 지우는 조건: TTL, logout, order completed, flush completed\n"
            "- 삭제 또는 eviction이 실행되는 코드 위치\n"
            "- 큐/캐시/log buffer의 모니터링 지표 알람 설정\n\n"
            "코드 리뷰 체크리스트 (CONV-MEM-011):\n"
            "□ 무한 증가하는 list/dict가 있는가?\n"
            "□ 캐시에 maxsize/TTL/clear 정책이 있는가?\n"
            "□ 큐가 bounded인가? (Queue(maxsize=0)은 unbounded)\n"
            "□ 대용량 데이터를 한 번에 읽는가? (pagination, streaming, chunk 처리 필요)\n"
            "□ 임시 데이터가 작업 후 제거되는가?\n"
            "□ 모니터링이 있는가? (cache size, queue size, RSS, GC, tracemalloc)"
        ),
    },
]

# ── UUID 헬퍼 ─────────────────────────────────────────────────────────────────

def _doc_id() -> str:
    return str(uuid.uuid5(_NS, f"m3-doc-{DOC_STEM}"))


def _chunk_id(section: str) -> str:
    return str(uuid.uuid5(_NS, f"m3-chunk-{DOC_STEM}-{section}"))


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
VALUES (%s, %s, 'upload', 'docx', %s, %s, false, false,
        'stored', 'public', 'all', NOW(), NOW())
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
    embedding  = EXCLUDED.embedding,
    model_name = EXCLUDED.model_name,
    content    = EXCLUDED.content,
    metadata   = EXCLUDED.metadata
"""


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main(dry_run: bool = False) -> None:
    enable_write = os.getenv("ENABLE_DB_WRITE", "false").lower() == "true"
    if not dry_run and not enable_write:
        print("[abort] ENABLE_DB_WRITE=true 가 아닌 상태에서는 실행 불가.")
        sys.exit(1)

    print(f"[index_memory_leak] {len(CHUNKS)}개 청크 임베딩 시작 (bge-m3)...")
    texts = [c["text"] for c in CHUNKS]
    vectors = embed_texts(texts)
    print(f"[index_memory_leak] 임베딩 완료 — 벡터 {len(vectors)}개, 차원 {len(vectors[0])}")

    if dry_run:
        print("\n[dry-run] DB 쓰기 없음. 파싱 결과:")
        for c, vec in zip(CHUNKS, vectors):
            cid = _chunk_id(c["section"])
            print(f"  {cid[:8]}… | {RULE_ID} | {c['section']} | {len(c['text'])}자 | dim={len(vec)}")
        return

    conn = _get_conn()
    cur = conn.cursor()

    # ① document UPSERT (1행)
    did = _doc_id()
    cur.execute(_DOC_UPSERT, (
        did,
        f"M3 코드리뷰 규칙: {RULE_ID} — Memory Leak Unbounded Collection",
        CATEGORY,
        STORAGE_PATH,
    ))
    print(f"[index_memory_leak] documents UPSERT — doc_id={did[:8]}…")

    # ② chunks UPSERT
    for chunk in CHUNKS:
        cid = _chunk_id(chunk["section"])
        tok = max(1, len(chunk["text"].split()))
        cur.execute(_CHUNK_UPSERT, (
            cid, did, chunk["text"], tok,
            chunk["section"], STORAGE_PATH,
        ))
    print(f"[index_memory_leak] chunks UPSERT — {len(CHUNKS)}행")

    # ③ chunk_embeddings UPSERT
    for chunk, vec in zip(CHUNKS, vectors):
        cid = _chunk_id(chunk["section"])
        meta = json.dumps({
            "category":        CATEGORY,
            "storage_path":    STORAGE_PATH,
            "section_header":  chunk["section"],
            "rule_id":         RULE_ID,
            "severity":        SEVERITY,
            "embedding_model": EMBEDDING_MODEL,
        }, ensure_ascii=False)
        cur.execute(_EMB_UPSERT, (cid, vec, EMBEDDING_MODEL, chunk["text"], meta))
    print(f"[index_memory_leak] chunk_embeddings UPSERT — {len(CHUNKS)}행")

    conn.commit()
    cur.close()
    conn.close()

    print(f"\n[index_memory_leak] 완료. {RULE_ID} {len(CHUNKS)}개 청크 인덱싱됨.")
    print("ENABLE_DB_WRITE=false 로 복구하세요 (override 파일 또는 .env).")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    main(dry_run=dry_run)
