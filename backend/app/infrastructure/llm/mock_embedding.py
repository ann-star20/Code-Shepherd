"""MockEmbeddingService — 로컬 TDD용 결정론적 Bag-of-Words 임베딩 서비스.

build_process.md §3 사양:
  - API 호출 없이 텍스트 기반 항상 멱등적 768차원 벡터 반환
  - camelCase·PascalCase 분해 + Bag-of-Words 해시로
    의미적으로 유사한 키워드를 공유하는 텍스트 간 높은 코사인 유사도 자연 발생
    (예: CrossSiteRequestForgery ↔ CSRF ↔ Cross-Site Request Forgery → 코사인 > 0.85)
  - L2 정규화(Normalization) 수행 → 코사인 유사도 = 내적 연산
"""
from __future__ import annotations

import hashlib
import math
import re

DIM = 1024
# DIM = 768


def _tokenize(text: str) -> list[str]:
    """camelCase·PascalCase 분해 + 구분자 분할 → 소문자 토큰 목록.

    예시:
      "CrossSiteRequestForgery" → ["cross", "site", "request", "forgery"]
      "XSS Attack"              → ["xss", "attack"]
      "크로스 사이트"            → ["크로스", "사이트"]
    """
    # camelCase → "camel Case"
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    # "ABCDef" → "ABC Def"
    text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", text)
    return re.findall(r"[a-zA-Z0-9가-힣]+", text.lower())


def bag_embed(text: str, dim: int = DIM) -> list[float]:
    """단어 가방(Bag-of-Words) 해시 임베딩 → L2 정규화 벡터.

    각 토큰을 SHA-256 해시로 dim개 빈(bin) 중 하나에 누적하여 희소 정수 벡터를 만든 뒤
    L2 정규화한다. 같은 단어 집합을 많이 공유하는 텍스트는 코사인 유사도가 높다.
    """
    tokens = _tokenize(text)
    vec = [0.0] * dim
    for token in tokens:
        idx = int(hashlib.sha256(token.encode()).hexdigest(), 16) % dim
        vec[idx] += 1.0
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec] if norm > 0 else vec


def cosine_sim(a: list[float], b: list[float]) -> float:
    """L2-정규화된 두 벡터의 코사인 유사도 = 내적."""
    return max(-1.0, min(1.0, sum(x * y for x, y in zip(a, b))))


class MockEmbeddingService:
    """API 비용 없는 결정론적 Bag-of-Words 임베딩 서비스.

    동일 텍스트 → 동일 벡터 (멱등성).
    의미적으로 겹치는 키워드를 공유하는 텍스트 → 높은 코사인 유사도.
    """

    def embed(self, text: str) -> list[float]:
        return bag_embed(text)
