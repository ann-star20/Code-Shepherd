"""
Gemini LLM 싱글턴 + tenacity 재시도 래퍼.

파이프라인 스테이지별 두 가지 LLM 경로를 제공한다.

Fast path  (stage1·stage2·stage5b): thinking_budget=0, temperature=1
  - Google API 제약: thinking_budget=0이면 temperature는 반드시 1
  - 변환·검증처럼 기준이 명확한 작업 → latency 우선

Quality path (stage5 메타데이터 추출): thinking 활성화, temperature=0.5
  - 카테고리 분류처럼 모호한 판단이 필요한 작업 → 정확도 우선
  - 문서당 1회 호출이므로 +3~5초 추가 레이턴시 허용

- 프로세스당 인스턴스 각 1개 유지 (싱글턴)
- call_gemini_with_retry(): fast path, 최대 2회 재시도
- call_gemini_quality(): quality path, 최대 2회 재시도
"""

from __future__ import annotations

import logging
import os
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GEMINI_THINKING_BUDGET = int(os.getenv("GEMINI_THINKING_BUDGET", "1024"))

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except ImportError:
    ChatGoogleGenerativeAI = None  # type: ignore[assignment,misc]

_gemini_llm = None
_gemini_llm_quality = None


def _get_gemini_llm() -> Any:
    """
    Fast path 싱글턴: thinking 비활성화, latency 우선.

    thinking_budget=0이면 Google API가 temperature=1을 강제한다.
    Stage1(변환), Stage2(검증), Stage5b(메타데이터 검증)에 사용.
    """
    global _gemini_llm
    if _gemini_llm is None:
        init_kwargs: dict = {
            "model": GEMINI_MODEL,
            "google_api_key": GEMINI_API_KEY,
            "temperature": 1,  # thinking_budget=0 시 API 강제값
        }
        if "2.5" in GEMINI_MODEL:
            init_kwargs["thinking_budget"] = 0
        _gemini_llm = ChatGoogleGenerativeAI(**init_kwargs)
    return _gemini_llm


def _get_gemini_llm_quality() -> Any:
    """
    Quality path 싱글턴: thinking 활성화, 정확도 우선.

    thinking을 활성화하면 temperature를 자유롭게 설정할 수 있다.
    카테고리 분류처럼 모호한 판단이 필요한 Stage5 메타데이터 추출에 사용.
    """
    global _gemini_llm_quality
    if _gemini_llm_quality is None:
        init_kwargs: dict = {
            "model": GEMINI_MODEL,
            "google_api_key": GEMINI_API_KEY,
            "temperature": 0.1,
        }
        if "2.5" in GEMINI_MODEL:
            init_kwargs["thinking_budget"] = GEMINI_THINKING_BUDGET
        _gemini_llm_quality = ChatGoogleGenerativeAI(**init_kwargs)
    return _gemini_llm_quality


def parse_gemini_json(raw: str) -> dict:
    """Gemini 응답에서 JSON 객체를 파싱한다.

    Gemini는 가끔 ```json ... ``` 코드 블록으로 감싸서 반환한다.
    이 함수는 그 wrapper를 제거하고 순수 JSON만 파싱한다.

    Raises:
        json.JSONDecodeError: JSON 파싱에 실패한 경우
    """
    import json

    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        inner = parts[1] if len(parts) > 1 else ""
        if inner.startswith("json"):
            inner = inner[4:]
        raw = inner.strip()
    return json.loads(raw)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
async def call_gemini_with_retry(messages: list) -> Any:
    """
    Fast path: thinking 비활성화, 최대 2회 재시도.
    Stage1·Stage2·Stage5b에서 사용.
    """
    llm = _get_gemini_llm()
    return await llm.ainvoke(messages)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
async def call_gemini_quality(messages: list) -> Any:
    """
    Quality path: thinking 활성화, 최대 2회 재시도.
    Stage5 메타데이터 추출에서 사용 (카테고리 분류 정확도 우선).
    """
    llm = _get_gemini_llm_quality()
    return await llm.ainvoke(messages)
