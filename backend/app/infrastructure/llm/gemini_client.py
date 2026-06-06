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
        allowed_domains = metadata.get("allowed_domains")
        prompt = _build_prompt(text_chunk, metadata, allowed_domains)
        response = await self._model.generate_content_async(prompt)
        raw_list = _parse_json_safely(response.text)
        return [ConceptExtractionSchema(**item) for item in raw_list]

    def is_tracing_enabled(self) -> bool:
        return True


DEFAULT_DOMAINS = ["security", "performance"]


def _build_prompt(
    text_chunk: str,
    metadata: dict,
    allowed_domains: list[str] | None = None,
) -> str:
    """Extractor 프롬프트 빌더.

    allowed_domains: domain_registry에서 주입. None이면 DEFAULT_DOMAINS 사용.
    새 도메인 추가 시 이 함수는 수정 불필요.
    """
    framework = metadata.get("framework", "Unknown")
    lang = metadata.get("lang", "EN")
    domains = allowed_domains if allowed_domains else DEFAULT_DOMAINS
    domain_values = ", ".join(f'"{d}"' for d in domains)

    return (
        f"아래 공식 문서 청크({framework}, {lang})에서 개념을 추출하고 "
        "JSON 배열로만 응답하라. 각 항목은 아래 스키마를 정확히 따를 것.\n\n"
        "필수 필드:\n"
        '  "concept_name": str  — 영문 표준 약어 (예: "XSS", "N+1Query")\n'
        f'  "domains": list[str] — 허용값: {domain_values}.\n'
        "    단일 도메인 또는 교차 도메인 배열로 지정. "
        '"both" 사용 금지. 미등록 도메인도 그대로 포함(시스템이 DOMAIN_PENDING 처리).\n'
        '  "severity": "CRITICAL"|"HIGH"|"MEDIUM"|"LOW"\n'
        '  "description_ko": str  — 한국어 설명\n\n'
        "선택 필드: concept_type, cwe_id, owasp_id, aliases, "
        "security_mechanisms, affected_components, config_properties, root_cause\n\n"
        f"---\n{text_chunk}\n---"
    )
