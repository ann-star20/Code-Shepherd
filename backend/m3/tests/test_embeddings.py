"""src/embeddings.py 단위테스트 — provider 전환·캐시·차원 검증 (네트워크 mock)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src import config
from src import embeddings


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    d = tmp_path / "embed_cache"
    monkeypatch.setattr(config, "EMBED_CACHE_DIR", str(d))
    return d


def _fake_ollama_response(dims: int, count: int):
    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"embeddings": [[0.1] * dims for _ in range(count)]}

    return _Resp()


# ── ollama 경로 ───────────────────────────────────────────────────────────────

def test_ollama_provider_embeds_and_caches(cache_dir, monkeypatch):
    monkeypatch.setattr(config, "EMBEDDING_PROVIDER", "ollama")
    calls = []

    def fake_post(url, json=None, timeout=None):
        calls.append(json["input"])
        return _fake_ollama_response(1024, len(json["input"]))

    monkeypatch.setattr(embeddings.httpx, "post", fake_post)

    vecs = embeddings.embed_texts(["hello", "world"])
    assert len(vecs) == 2
    assert len(vecs[0]) == 1024
    assert len(calls) == 1  # 배치 1회 호출

    # 두 번째 호출은 전부 캐시 히트 — API 미호출
    vecs2 = embeddings.embed_texts(["hello", "world"])
    assert vecs2 == vecs
    assert len(calls) == 1


def test_ollama_dim_mismatch_raises(cache_dir, monkeypatch):
    monkeypatch.setattr(config, "EMBEDDING_PROVIDER", "ollama")
    monkeypatch.setattr(
        embeddings.httpx, "post",
        lambda url, json=None, timeout=None: _fake_ollama_response(768, len(json["input"])),
    )
    with pytest.raises(RuntimeError, match="1024"):
        embeddings.embed_texts(["bad dims"])


# ── openai 폴백 경로 ──────────────────────────────────────────────────────────

def test_openai_provider_used_when_configured(cache_dir, monkeypatch):
    monkeypatch.setattr(config, "EMBEDDING_PROVIDER", "openai")

    class _FakeData:
        def __init__(self):
            self.embedding = [0.2] * 1536

    class _FakeClient:
        class embeddings:  # noqa: N801
            @staticmethod
            def create(model, input):
                class _R:
                    data = [_FakeData() for _ in input]
                return _R()

    monkeypatch.setattr(embeddings, "_get_openai", lambda: _FakeClient())

    vecs = embeddings.embed_texts(["fallback test"])
    assert len(vecs) == 1
    assert len(vecs[0]) == 1536


# ── 캐시 키 분리 ──────────────────────────────────────────────────────────────

def test_cache_keys_differ_by_model(cache_dir, monkeypatch):
    """같은 텍스트라도 provider(모델)가 다르면 캐시 파일이 분리되어야 한다."""
    monkeypatch.setattr(config, "EMBEDDING_PROVIDER", "ollama")
    monkeypatch.setattr(
        embeddings.httpx, "post",
        lambda url, json=None, timeout=None: _fake_ollama_response(1024, len(json["input"])),
    )
    embeddings.embed_texts(["same text"])
    files_after_ollama = set(cache_dir.glob("*.json"))
    assert len(files_after_ollama) == 1

    monkeypatch.setattr(config, "EMBEDDING_PROVIDER", "openai")

    class _FakeData:
        embedding = [0.3] * 1536

    class _FakeClient:
        class embeddings:  # noqa: N801
            @staticmethod
            def create(model, input):
                class _R:
                    data = [_FakeData() for _ in input]
                return _R()

    monkeypatch.setattr(embeddings, "_get_openai", lambda: _FakeClient())
    embeddings.embed_texts(["same text"])
    files_after_both = set(cache_dir.glob("*.json"))
    assert len(files_after_both) == 2  # 모델별 키 분리


def test_active_model_names():
    assert embeddings._active_model("ollama") == config.OLLAMA_EMBED_MODEL
    assert embeddings._active_model("openai") == config.EMBEDDING_MODEL
