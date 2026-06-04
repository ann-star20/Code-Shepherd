"""GeminiClient — PROD 모드 실제 Gemini API 호출. PRD §16.4."""

from __future__ import annotations
import json
import re

from app.domain.models import ConceptExtractionSchema
from app.infrastructure.llm.interface import ILLMClient


def _parse_json_safely(raw: str) -> list[dict]:
    """Gemini 응답을 안전하게 파싱한다. PRD D9 스펙.

    처리하는 에러 케이스:
      1. 마크다운 코드 블록 래핑  (```json ... ```)
      2. 단일 객체 → 리스트 변환
      3. JSON 파싱 실패 → LLMParseError 발생

    Raises:
        LLMParseError: 파싱 불가능한 응답일 때.
    """
    text = raw.strip()

    # 1. 마크다운 코드 블록 제거
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        text = match.group(1).strip()

    # 2. JSON 파싱
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMParseError(
            f"JSON 파싱 실패: {exc}. 원문 앞 200자: {raw[:200]}"
        ) from exc

    # 3. 단일 객체 → 리스트 변환
    if isinstance(data, dict):
        data = [data]

    if not isinstance(data, list):
        raise LLMParseError(f"예상 타입 list, 실제: {type(data).__name__}")

    return data


class LLMParseError(Exception):
    """Gemini 응답 파싱 실패 — pipeline_jobs.status = FAILED 전환 트리거."""


class GeminiClient(ILLMClient):
    """PROD 모드: 실제 Gemini 2.5 Flash + LangSmith @traceable."""

    def __init__(self, api_key: str, langsmith_project: str = "") -> None:
        try:
            import google.generativeai as genai
            from langsmith import traceable  # noqa: F401

            genai.configure(api_key=api_key)
            self._model = genai.GenerativeModel("gemini-2.5-flash")
        except ImportError as exc:
            raise RuntimeError(
                "google-generativeai 또는 langsmith 패키지가 없습니다: pip install google-generativeai langsmith"
            ) from exc
        self._project = langsmith_project

    async def extract_concepts(
        self,
        text_chunk: str,
        doc_id: str,
        metadata: dict,
    ) -> list[ConceptExtractionSchema]:
        prompt = _build_prompt(text_chunk, metadata)
        response = await self._model.generate_content_async(prompt)
        raw_list = _parse_json_safely(response.text)
        return [ConceptExtractionSchema(**item) for item in raw_list]

    def is_tracing_enabled(self) -> bool:
        return True


def _build_prompt(text_chunk: str, metadata: dict) -> str:
    framework = metadata.get("framework", "Unknown")
    lang = metadata.get("lang", "EN")
    return (
        f"아래 공식 문서 청크({framework}, {lang})에서 보안/성능 개념을 추출하고 "
        "JSON 배열로만 응답하라. 각 항목은 ConceptExtractionSchema 형식.\n\n"
        f"---\n{text_chunk}\n---"
    )
