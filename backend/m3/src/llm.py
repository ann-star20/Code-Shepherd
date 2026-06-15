"""LLM 호출 래퍼 — 모든 Anthropic 호출은 이 모듈만 거친다.

책임 (브리프 §5.3-6, §9):
1. src/config.py 의 MODELS/PROMPT_VERSIONS/MAX_TOKENS 만 사용 (하드코딩 금지)
2. 호출마다 로깅: node, model, prompt_version, cache_hit, latency_ms
3. 디스크 캐시: sha256(모델명+시스템+사용자) → .cache/llm/ (temperature 0 → 무손실)
4. Anthropic 프롬프트 캐싱: system 메시지에 cache_control 적용 (고정 프리픽스)
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from src.config import LLM_CACHE_DIR, MAX_TOKENS, MODELS, PROMPT_VERSIONS, TEMPERATURE

load_dotenv()

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def call_llm(node: str, system_prefix: str, user_suffix: str) -> str:
    """노드 1회 호출. 반환: 모델 텍스트 응답 (디스크 캐시 히트 시 API 미호출)."""
    model = MODELS[node]
    prompt_version = PROMPT_VERSIONS[node]
    max_tokens = MAX_TOKENS[node]

    cache_key = hashlib.sha256(
        f"{model}\n{system_prefix}\n{user_suffix}".encode("utf-8")
    ).hexdigest()
    cache_dir = Path(LLM_CACHE_DIR)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{cache_key}.txt"

    if cache_file.exists():
        print(
            f"[llm] node={node} model={model} prompt={prompt_version} "
            f"cache_hit=True",
            flush=True,
        )
        return cache_file.read_text(encoding="utf-8")

    t0 = time.time()
    resp = _get_client().messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=TEMPERATURE,
        system=[
            {
                "type": "text",
                "text": system_prefix,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_suffix}],
    )
    latency_ms = int((time.time() - t0) * 1000)

    result = resp.content[0].text
    cache_file.write_text(result, encoding="utf-8")

    print(
        f"[llm] node={node} model={model} prompt={prompt_version} "
        f"cache_hit=False latency_ms={latency_ms}",
        flush=True,
    )
    return result
