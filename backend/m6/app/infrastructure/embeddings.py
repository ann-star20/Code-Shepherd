from __future__ import annotations

import logging
import os

import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
_DIM = 1024
_ZERO_VEC: list[float] = [0.0] * _DIM


class BgeEmbeddingClient:
    """BAAI/bge-m3 로컬 SentenceTransformer 래퍼."""

    def __init__(self, model_name: str = _MODEL_NAME) -> None:
        logger.info("[BgeEmbeddingClient] 로컬 %s 로드 시작...", model_name)
        self._model = SentenceTransformer(model_name)
        logger.info("[BgeEmbeddingClient] 로드 완료 — 1024차원 임베딩 준비.")

    def embed(self, text: str) -> list[float]:
        if not text or not text.strip():
            return _ZERO_VEC
        vec: np.ndarray = self._model.encode(text, convert_to_numpy=True)
        norm = np.linalg.norm(vec)
        return (vec / norm).tolist() if norm > 0 else vec.tolist()

    def get_embedding(self, text: str) -> list[float]:
        return self.embed(text)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vecs: np.ndarray = self._model.encode(
            texts, convert_to_numpy=True, batch_size=32
        )
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms = np.where(norms > 0, norms, 1.0)
        return (vecs / norms).tolist()


_client: BgeEmbeddingClient | None = None


def get_client() -> BgeEmbeddingClient:
    global _client
    if _client is None:
        _client = BgeEmbeddingClient()
    return _client
