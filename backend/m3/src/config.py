"""설정 단일 관리 지점 — 모델명·프롬프트 버전·임계값은 전부 여기서만 (하드코딩 금지).

규칙 (CLAUDE.md / 브리프 §5.3-6):
- 모든 LLM 호출은 src/llm.py 래퍼를 거치며, 모델명+프롬프트 버전을 로깅한다.
- temperature 0 고정. D3 튜닝 완료 전 모델 변경 금지, ④ judge 다운그레이드 영구 금지.
"""
from __future__ import annotations

import os

# ── LLM 모델 (노드별 — 전 노드 sonnet, D4에 ⑤만 조건부 Haiku 검토: 브리프 §9.5) ──
TEMPERATURE: float = 0.0
MODELS: dict[str, str] = {
    "extract_concepts": "claude-sonnet-4-6",
    "check_sufficiency": "claude-sonnet-4-6",
    "judge": "claude-sonnet-4-6",          # 영구 고정 — 다운그레이드 금지
    "compose_comment": "claude-sonnet-4-6",
}

# ── 프롬프트 버전 (프롬프트 파일/문자열 수정 시 반드시 버전 올릴 것) ──
PROMPT_VERSIONS: dict[str, str] = {
    "extract_concepts": "v1",
    "check_sufficiency": "v1",
    "judge": "v1",
    "compose_comment": "v1",
}

# ── 토큰 상한 (브리프 §9.4 입력 다이어트) ──
MAX_TOKENS: dict[str, int] = {
    "extract_concepts": 800,
    "check_sufficiency": 800,
    "judge": 2000,
    "compose_comment": 800,
}

# ── 임베딩 / 벡터스토어 (통합 불변조건: 기본 bge-m3(ollama, 1024d), openai 폴백) ──
# 전환은 .env 만으로: EMBEDDING_PROVIDER / OLLAMA_BASE_URL(도커=host.docker.internal)
EMBEDDING_PROVIDER: str = os.getenv("EMBEDDING_PROVIDER", "ollama")
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBED_MODEL: str = os.getenv("OLLAMA_EMBED_MODEL", "bge-m3")
EMBEDDING_MODEL: str = "text-embedding-3-small"   # openai 폴백 모델
EMBEDDING_DIMS: dict[str, int] = {"ollama": 1024, "openai": 1536}
CHROMA_DIR: str = os.getenv("CHROMA_DIR", ".chroma")
CHROMA_COLLECTION: str = "kms_rules"
CORPUS_DIR: str = "corpus"

# ── 검색·충분성 판단 (브리프 §2.5 기본값 — D3 튜닝 대상) ──
SYNONYMS_PER_CONCEPT: int = 3
TOP_K: int = 5                  # query 당 top-k
MAX_REQUERY: int = 1            # 전 파이프라인 합산 상한 (contracts: requery_count)
MAX_JUDGE_CHUNKS: int = 8       # judge 입력 청크 dedup 후 캡 (6~8)

# ── 캐시 (브리프 §9.1 — D2부터 필수) ──
LLM_CACHE_DIR: str = os.getenv("LLM_CACHE_DIR", ".cache/llm")
EMBED_CACHE_DIR: str = os.getenv("EMBED_CACHE_DIR", ".cache/embed")
