"""② retrieve — queries → chunks (top-k 5/query, dedup)

계약: contracts/README.md 표 ②. Chroma 로컬 컬렉션 검색.
임베딩: src/embeddings.embed_texts — 인덱스와 질의가 반드시 같은 provider/model.
컬렉션 metadata 의 embedding_model 과 현재 설정이 다르면 즉시 에러 (조용한 오염 방지).
"""
from __future__ import annotations

import chromadb
from dotenv import load_dotenv

from contracts import Chunk, ReviewState
from src.config import CHROMA_COLLECTION, CHROMA_DIR, MAX_JUDGE_CHUNKS, TOP_K
from src.embeddings import _active_model, embed_texts

load_dotenv()

_chroma_collection = None


def _get_collection():
    global _chroma_collection
    if _chroma_collection is None:
        client = chromadb.PersistentClient(path=CHROMA_DIR)
        _chroma_collection = client.get_collection(CHROMA_COLLECTION)
        idx_model = (_chroma_collection.metadata or {}).get("embedding_model")
        if idx_model and idx_model != _active_model():
            raise RuntimeError(
                f"인덱스/질의 임베딩 불일치: 인덱스={idx_model}, 현재 설정={_active_model()} "
                "— EMBEDDING_PROVIDER 확인 후 make reindex 필요"
            )
    return _chroma_collection


def _embed(text: str) -> list[float]:
    return embed_texts([text])[0]


def retrieve(state: ReviewState) -> dict:
    queries: list[str] = state.get("queries", [])
    if not queries:
        return {"chunks": []}

    collection = _get_collection()
    seen_ids: set[str] = set()
    chunks: list[Chunk] = []

    for query in queries:
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
        if len(chunks) >= MAX_JUDGE_CHUNKS:
            break

    chunks = chunks[:MAX_JUDGE_CHUNKS]
    return {"chunks": chunks}
