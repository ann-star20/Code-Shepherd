#!/usr/bin/env python3
"""
KMS 문서 직접 임베딩 스크립트 (m0 연동 전 임시)
실행: python scripts/embed_kms_docs.py

필요 패키지 (설치 안 돼있으면):
  pip install python-docx pypdf asyncpg httpx python-dotenv
"""

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import asyncpg
import httpx
from dotenv import load_dotenv

# 루트 .env 로드
load_dotenv(Path(__file__).parent.parent.parent.parent / ".env")

# --- Config ---
DB_HOST     = os.environ["DB_HOST"]
DB_PORT     = int(os.environ.get("DB_PORT", "5432"))
DB_NAME     = os.environ["DB_NAME"]
DB_USER     = os.environ["DB_USER"]
DB_PASSWORD = os.environ["DB_PASSWORD"]

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.environ.get("OLLAMA_EMBEDDING_MODEL", "bge-m3")

KMS_DIR    = Path(__file__).parent.parent / "data" / "kms"
CHUNK_SIZE = 500  # characters per chunk

# 폴더명 → documents.category (CHECK 제약: '코딩컨벤션','아키텍처','온보딩','보안','배포','기타')
DOCUMENTS_CATEGORY = {
    "security_guide":    "보안",
    "coding_convention": "코딩컨벤션",
    "learning_resource": "기타",
}

# 폴더명 → chunk_embeddings.metadata.category (RAG 검색 필터 — learn_pipeline.py의 rag_search() category와 일치해야 함)
METADATA_CATEGORY = {
    "security_guide":    "보안",
    "coding_convention": "코딩컨벤션",
    "learning_resource": "코드성능검증",
}


# --- Text extraction ---

def extract_docx(path: Path) -> list[str]:
    from docx import Document
    doc = Document(str(path))
    return [p.text.strip() for p in doc.paragraphs if p.text.strip()]


def extract_pdf(path: Path) -> list[str]:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text and text.strip():
            pages.append(text.strip())
    return pages


def make_chunks(texts: list[str]) -> list[str]:
    full = "\n".join(texts)
    return [
        full[i : i + CHUNK_SIZE].strip()
        for i in range(0, len(full), CHUNK_SIZE)
        if full[i : i + CHUNK_SIZE].strip()
    ]


# --- Ollama embedding ---

async def embed(text: str) -> list[float]:
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{OLLAMA_BASE_URL}/api/embeddings",
            json={"model": OLLAMA_MODEL, "prompt": text},
        )
        resp.raise_for_status()
        return resp.json()["embedding"]


# --- DB insertion ---

async def insert_file(conn: asyncpg.Connection, file_path: Path, category: str) -> int:
    # 이미 임베딩된 파일이면 스킵 (idempotent)
    exists = await conn.fetchval(
        "SELECT 1 FROM documents WHERE title = $1 AND source = 'upload'",
        file_path.stem,
    )
    if exists:
        print(f"    [SKIP] 이미 임베딩됨: {file_path.name}")
        return 0

    # 텍스트 추출
    if file_path.suffix == ".docx":
        texts = extract_docx(file_path)
    elif file_path.suffix == ".pdf":
        texts = extract_pdf(file_path)
    else:
        return 0

    chunks = make_chunks(texts)
    if not chunks:
        print(f"    [SKIP] 텍스트 없음: {file_path.name}")
        return 0

    # 1. documents 테이블에 메타데이터 삽입
    doc_id = str(uuid.uuid4())
    await conn.execute(
        """
        INSERT INTO documents (doc_id, title, source, category, file_type, upload_status)
        VALUES ($1, $2, 'upload', $3, $4, 'stored')
        """,
        doc_id,
        file_path.stem,
        DOCUMENTS_CATEGORY[category],
        file_path.suffix.lstrip("."),
    )

    # metadata JSONB — category 값이 RAG 검색 필터 기준
    metadata = json.dumps({
        "category": METADATA_CATEGORY[category],  # RAG 검색 필터: 보안 / 코딩컨벤션 / 코드성능검증
        "source":   "m4-kms-seed",
        "file":     file_path.name,
    })

    # 2. 청크별 chunks + chunk_embeddings 삽입
    for i, chunk_text in enumerate(chunks, 1):
        chunk_id = str(uuid.uuid4())

        await conn.execute(
            """
            INSERT INTO chunks (chunk_id, doc_id, chunk_type, content, trace_id)
            VALUES ($1, $2, 'child', $3, 'm4-kms')
            """,
            chunk_id, doc_id, chunk_text,
        )

        vector = await embed(chunk_text)
        vector_str = "[" + ",".join(str(v) for v in vector) + "]"

        await conn.execute(
            """
            INSERT INTO chunk_embeddings (chunk_id, embedding, model_name, content, metadata)
            VALUES ($1, $2::vector, $3, $4, $5::jsonb)
            """,
            chunk_id, vector_str, OLLAMA_MODEL, chunk_text, metadata,
        )

        print(f"    {i}/{len(chunks)} 청크 저장 중...", end="\r")

    print(f"    ✓ {len(chunks)}개 청크 완료: {file_path.name}          ")
    return len(chunks)


async def main():
    print(f"KMS 임베딩 시작")
    print(f"  모델 : {OLLAMA_MODEL}")
    print(f"  DB   : {DB_HOST}:{DB_PORT}/{DB_NAME}")
    print(f"  경로 : {KMS_DIR}\n")

    conn = await asyncpg.connect(
        host=DB_HOST, port=DB_PORT,
        database=DB_NAME, user=DB_USER, password=DB_PASSWORD,
    )
    total = 0
    try:
        for category in ["security_guide", "coding_convention", "learning_resource"]:
            folder = KMS_DIR / category
            if not folder.exists():
                print(f"[{category}] 폴더 없음 — 건너뜀")
                continue

            files = sorted(folder.glob("*.docx")) + sorted(folder.glob("*.pdf"))
            print(f"[{category}] 파일 {len(files)}개")
            for f in files:
                total += await insert_file(conn, f, category)
    finally:
        await conn.close()

    print(f"\n완료 — 총 {total}개 청크 Cloud SQL에 저장됨")


if __name__ == "__main__":
    asyncio.run(main())
