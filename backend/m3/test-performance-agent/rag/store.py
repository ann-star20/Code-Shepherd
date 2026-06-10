"""pgvector 리터럴 헬퍼 — 저장·검색이 공유하는 벡터 표현 단일 출처.

적재는 KMS(m0)가 chunks/chunk_embeddings 에 한다 — m3 는 검색(retriever)만.
(옛 목업 convention_embeddings 테이블·DDL 은 제거됨 — KMS 테이블만 사용.)
"""
from __future__ import annotations


def to_vector_literal(vec: list[float]) -> str:
    """pgvector 리터럴 '[0.1,0.2,...]' (어댑터 없이 %s::vector 캐스팅용).

    적재(KMS)·검색(retriever)이 같은 표현을 쓴다 — 표현 형식 단일 출처.
    """
    return "[" + ",".join(str(float(x)) for x in vec) + "]"
