"""임베딩 단일 진입점 — provider 전환(.env) + 디스크 캐시 (ingestion·retrieve 공용).

통합 불변조건: 기본 bge-m3(ollama, 1024d), openai text-embedding-3-small(1536d)은 폴백.
환경 전환은 .env 만으로 — EMBEDDING_PROVIDER, OLLAMA_BASE_URL(도커=host.docker.internal).

캐시 키: sha256(모델명 + 텍스트) → 모델별 자동 분리 (1024d/1536d 혼입 불가).
차원 검증: provider 기대 차원과 불일치 시 즉시 RuntimeError (조용한 인덱스 오염 방지).
ollama 장애 시 자동 폴백하지 않는다 — 인덱스와 질의의 provider 가 어긋나면 검색이
조용히 무의미해지므로, 명시적으로 EMBEDDING_PROVIDER=openai + make reindex 를 안내한다.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
from openai import OpenAI

from src import config

_openai: OpenAI | None = None


def _get_openai() -> OpenAI:
    global _openai
    if _openai is None:
        _openai = OpenAI()
    return _openai


def _active_model(provider: str | None = None) -> str:
    p = provider or config.EMBEDDING_PROVIDER
    return config.OLLAMA_EMBED_MODEL if p == "ollama" else config.EMBEDDING_MODEL


def _cache_path(model: str, text: str) -> Path:
    key = hashlib.sha256(f"{model}\n{text}".encode()).hexdigest()
    return Path(config.EMBED_CACHE_DIR) / f"{key}.json"


def _embed_ollama(texts: list[str]) -> list[list[float]]:
    try:
        resp = httpx.post(
            f"{config.OLLAMA_BASE_URL}/api/embed",
            json={"model": config.OLLAMA_EMBED_MODEL, "input": texts},
            timeout=120,
        )
        resp.raise_for_status()
    except Exception as exc:
        raise RuntimeError(
            f"ollama 임베딩 실패 ({type(exc).__name__}) — base_url={config.OLLAMA_BASE_URL}. "
            "폴백: .env 에 EMBEDDING_PROVIDER=openai 설정 후 make reindex"
        ) from exc
    return resp.json()["embeddings"]


def _embed_openai(texts: list[str]) -> list[list[float]]:
    resp = _get_openai().embeddings.create(model=config.EMBEDDING_MODEL, input=texts)
    return [d.embedding for d in resp.data]


def embed_texts(texts: list[str]) -> list[list[float]]:
    """텍스트 배치 → 벡터 (캐시 우선, 미캐시만 provider 호출)."""
    provider = config.EMBEDDING_PROVIDER
    model = _active_model(provider)
    expected_dims = config.EMBEDDING_DIMS.get(provider)

    cache_dir = Path(config.EMBED_CACHE_DIR)
    cache_dir.mkdir(parents=True, exist_ok=True)

    results: list[list[float] | None] = [None] * len(texts)
    pending: list[int] = []
    for i, text in enumerate(texts):
        cached = _cache_path(model, text)
        if cached.exists():
            results[i] = json.loads(cached.read_text(encoding="utf-8"))
        else:
            pending.append(i)

    if pending:
        batch = [texts[i] for i in pending]
        vecs = _embed_ollama(batch) if provider == "ollama" else _embed_openai(batch)
        for pos, idx in enumerate(pending):
            vec = vecs[pos]
            if expected_dims and len(vec) != expected_dims:
                raise RuntimeError(
                    f"임베딩 차원 불일치: provider={provider} model={model} "
                    f"기대 {expected_dims}d, 응답 {len(vec)}d — 모델 설정 확인 필요"
                )
            _cache_path(model, texts[idx]).write_text(json.dumps(vec), encoding="utf-8")
            results[idx] = vec

    print(f"[embed] provider={provider} model={model} "
          f"total={len(texts)} cache_hit={len(texts) - len(pending)}")
    return results  # type: ignore[return-value]
