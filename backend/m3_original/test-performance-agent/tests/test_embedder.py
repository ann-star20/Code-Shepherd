"""B1 — rag/embedder.py TDD (BGE-M3 공유 임베더, 절대규칙·위험 1).

저장(load_conventions)과 검색(retriever)이 둘 다 이 embed()만 쓴다.
실제 모델(BGE-M3 ~2GB) 없이 고립 테스트: _get_model을 monkeypatch한다.
"""
from rag import embedder


class _FakeModel:
    """sentence-transformers 모델 대역 — encode 호출만 흉내."""

    def __init__(self, dim: int = 1024):
        self.dim = dim
        self.calls: list = []

    def encode(self, texts, normalize_embeddings=False):
        self.calls.append((list(texts), normalize_embeddings))
        return [[0.1] * self.dim for _ in texts]


# ─── 1) 텍스트당 벡터 1개 ─────────────────────────────────────────────────────
def test_embed_returns_one_vector_per_text(monkeypatch):
    fake = _FakeModel()
    monkeypatch.setattr(embedder, "_get_model", lambda: fake)
    out = embedder.embed(["a", "b", "c"])
    assert len(out) == 3


# ─── 2) 차원 1024 + float ─────────────────────────────────────────────────────
def test_embed_dimension_is_1024(monkeypatch):
    fake = _FakeModel(dim=1024)
    monkeypatch.setattr(embedder, "_get_model", lambda: fake)
    out = embedder.embed(["hello"])
    assert len(out[0]) == 1024
    assert all(isinstance(x, float) for x in out[0])


# ─── 3) 빈 입력 → 빈 결과, 모델 로드도 안 함 ──────────────────────────────────
def test_embed_empty_input_no_model_load(monkeypatch):
    called = {"n": 0}

    def _boom():
        called["n"] += 1
        raise AssertionError("빈 입력엔 모델을 로드하면 안 됨")

    monkeypatch.setattr(embedder, "_get_model", _boom)
    assert embedder.embed([]) == []
    assert called["n"] == 0


# ─── 4) normalize=True 로 호출, 텍스트 그대로 전달 ────────────────────────────
def test_embed_normalizes_and_passes_texts(monkeypatch):
    fake = _FakeModel()
    monkeypatch.setattr(embedder, "_get_model", lambda: fake)
    embedder.embed(["x"])
    texts, normalize = fake.calls[0]
    assert texts == ["x"]
    assert normalize is True


# ─── 5) 모델/차원 설정값 (저장=검색 동일 보장의 단일 출처) ────────────────────
def test_embed_model_settings():
    from config import settings
    assert settings.EMBED_MODEL == "BAAI/bge-m3"
    assert settings.EMBED_DIM == 1024


# ─── 6) 오프라인 안전장치: 캐시 있으면 offline, 없으면 다운로드 ───────────────
def test_load_model_uses_cache_offline_first():
    """캐시 성공 → local_files_only=True만 시도(다운로드 안 함, stall 방지)."""
    calls = []

    def ctor(name, local_files_only):
        calls.append(local_files_only)
        return "MODEL_CACHED"

    m = embedder._load_model(ctor)
    assert m == "MODEL_CACHED"
    assert calls == [True]


def test_load_model_falls_back_to_download_when_no_cache():
    """캐시 없음(offline 실패) → 다운로드(local_files_only=False)로 폴백."""
    calls = []

    def ctor(name, local_files_only):
        calls.append(local_files_only)
        if local_files_only:
            raise OSError("not cached")
        return "MODEL_DOWNLOADED"

    m = embedder._load_model(ctor)
    assert m == "MODEL_DOWNLOADED"
    assert calls == [True, False]
