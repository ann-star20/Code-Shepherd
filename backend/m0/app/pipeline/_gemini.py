"""
Gemini LLM 싱글턴 + tenacity 재시도 래퍼.

모든 파이프라인 스테이지(stage1·stage2·stage5·stage5b)가 이 모듈을 통해
ChatGoogleGenerativeAI 인스턴스를 공유한다.

- 프로세스당 ChatGoogleGenerativeAI 인스턴스 1개 유지 (싱글턴)
- call_gemini_with_retry(): 최대 2회 재시도, 지수 백오프
"""

from __future__ import annotations

import logging
import os
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY", "")

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except ImportError:
    ChatGoogleGenerativeAI = None  # type: ignore[assignment,misc]

_gemini_llm = None


def _get_gemini_llm() -> Any:
    """
    ChatGoogleGenerativeAI 드라이버를 싱글턴으로 반환한다.
    호출당 LLM 인스턴스 생성 비용(인증·초기화)을 제거하기 위해
    모듈 수준에서 한 번만 생성하고 재사용한다.

    gemini-2.5-flash는 기본적으로 thinking을 활성화하므로
    단순 변환·검증 작업에서 응답이 30초를 초과할 수 있다.
    thinking_budget=0으로 비활성화해 속도를 확보한다.
    """
    global _gemini_llm
    if _gemini_llm is None:
        init_kwargs: dict = {
            "model": GEMINI_MODEL,
            "google_api_key": GEMINI_API_KEY,
            "temperature": 1,  # thinking_budget=0 시 temperature는 반드시 1
        }
        # gemini-2.5-* thinking 모델: thinking 비활성화로 레이턴시 감소
        if "2.5" in GEMINI_MODEL:
            init_kwargs["thinking_budget"] = 0
        _gemini_llm = ChatGoogleGenerativeAI(**init_kwargs)
    return _gemini_llm


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
        # ```json\n{...}\n``` 형태: parts[1]이 "json\n{...}\n"
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
    Gemini API를 호출하고 일시적 오류 시 최대 2회 재시도한다.
    (stop_after_attempt(3) = 최초 1회 + 재시도 2회)

    ResourceExhausted(429), InternalServerError(500), 네트워크 오류에 대응.
    JSON 파싱 실패 등 논리 오류는 호출자가 처리한다.
    """
    llm = _get_gemini_llm()
    return await llm.ainvoke(messages)
