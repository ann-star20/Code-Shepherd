"""BGE-M3 임베딩 — 저장·검색이 공유하는 단일 출처 (절대규칙·위험 1).

적재 스크립트(load_conventions)와 retriever 둘 다 이 embed()만 쓴다.
모델을 바꾸려면 여기(+config.settings.EMBED_MODEL)만 고친다 → 저장·검색 불일치 불가.

모델은 지연 로드(1회 캐시). 테스트에서는 _get_model을 monkeypatch해
실제 모델(약 2GB) 없이 고립한다.
"""
from __future__ import annotations

from config import settings

_model = None  # 지연 로드 캐시


def _model_ctor(name: str, local_files_only: bool):
    """실제 SentenceTransformer 생성자(주입 가능 — 테스트 고립용)."""
    from sentence_transformers import SentenceTransformer  # noqa: PLC0415

    return SentenceTransformer(name, local_files_only=local_files_only)


def _load_model(ctor=_model_ctor):
    """캐시 있으면 오프라인, 없으면 첫 다운로드.

    먼저 local_files_only=True 로 시도 → 캐시에 모델이 있으면 네트워크 접근 없이
    로드(불필요한 repo 전체 다운로드·stall 방지). 캐시에 없어 실패하면
    local_files_only=False 로 폴백해 첫 다운로드를 허용한다.
    """
    try:
        return ctor(settings.EMBED_MODEL, local_files_only=True)
    except Exception:
        return ctor(settings.EMBED_MODEL, local_files_only=False)


def _get_model():
    """BGE-M3 모델 지연 로드(1회). 테스트에서 monkeypatch 대상."""
    global _model
    if _model is None:
        _model = _load_model()
    return _model


def embed(texts: list[str]) -> list[list[float]]:
    """텍스트들을 BGE-M3로 임베딩 → 각 EMBED_DIM 차원 벡터(list[float]) 목록.

    저장·검색 공유 단일 진입점(절대규칙). 빈 입력 → 빈 리스트(모델 로드 안 함).
    normalize_embeddings=True → 코사인 검색에 적합한 단위 벡터.
    """
    if not texts:
        return []
    model = _get_model()
    vectors = model.encode(texts, normalize_embeddings=True)
    return [[float(x) for x in v] for v in vectors]
