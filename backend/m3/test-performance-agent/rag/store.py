"""convention_embeddings 테이블 — DDL + ensure (위험 2: 스키마 한 모듈 집중).

저장(load_conventions)·검색(retriever)이 공유하는 테이블 정의.
차원은 config.settings.EMBED_DIM(=BGE-M3 1024)에서 가져와 임베더와 항상 일치.
멱등(IF NOT EXISTS)이라 재실행 안전. ensure는 conn 주입(테스트 고립).
"""
from __future__ import annotations

from config import settings

CONVENTION_DDL = f"""
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS convention_embeddings (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    doc_title  text NOT NULL,
    source_url text NOT NULL DEFAULT '',
    content    text NOT NULL,
    embedding  vector({settings.EMBED_DIM}) NOT NULL
);
"""


def ensure_convention_table(conn) -> None:
    """convention_embeddings가 없으면 생성(확장 포함, 멱등). conn 주입."""
    with conn.cursor() as cur:
        cur.execute(CONVENTION_DDL)


def to_vector_literal(vec: list[float]) -> str:
    """pgvector 리터럴 '[0.1,0.2,...]' (어댑터 없이 %s::vector 캐스팅용).

    저장(load_conventions)·검색(retriever)이 공유 — 표현 형식 단일 출처.
    """
    return "[" + ",".join(str(float(x)) for x in vec) + "]"
