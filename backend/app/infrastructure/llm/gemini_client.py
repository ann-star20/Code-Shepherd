"""GeminiClient — PROD 모드 실제 Gemini API 호출. PRD §16.4."""

from __future__ import annotations
import json
import logging
import re

logger = logging.getLogger(__name__)

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

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash", langsmith_project: str = "") -> None:
        try:
            from google import genai
            from langsmith import traceable  # noqa: F401

            self._client = genai.Client(api_key=api_key)
            self._model_name = model
            logger.info("GeminiClient 초기화 — model: %s", model)
        except ImportError as exc:
            raise RuntimeError(
                "google-genai 또는 langsmith 패키지가 없습니다: pip install google-genai langsmith"
            ) from exc
        self._project = langsmith_project
        self.raw_responses: list[str] = []  # 청크별 LLM 원문 (--response-file 저장용)

    async def extract_concepts(
        self,
        text_chunk: str,
        doc_id: str,
        metadata: dict,
    ) -> list[ConceptExtractionSchema]:
        allowed_domains = metadata.get("allowed_domains")
        prompt = _build_prompt(text_chunk, metadata, allowed_domains)

        chunk_preview = text_chunk[:120].replace("\n", " ").strip()
        domains_used = allowed_domains or DEFAULT_DOMAINS
        logger.info(
            "[PROMPT] framework=%s lang=%s domains=%s chunk_len=%d | %.120s...",
            metadata.get("framework", "Unknown"),
            metadata.get("lang", "EN"),
            domains_used,
            len(text_chunk),
            chunk_preview,
        )

        response = await self._client.aio.models.generate_content(
            model=self._model_name, contents=prompt
        )

        self.raw_responses.append(response.text)
        logger.info("[RESPONSE RAW]\n%s", response.text)

        raw_list = _parse_json_safely(response.text)
        logger.info(
            "[PARSED] %d 개 컨셉: %s",
            len(raw_list),
            [r.get("concept_name") for r in raw_list],
        )

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
    domains = allowed_domains if allowed_domains else ["security", "performance"]
    domain_values = ", ".join(f'"{d}"' for d in domains)

    # 주의: JSON 스키마 부분의 중괄호({}) 충돌을 막기 위해, 
    # 변수 바인딩이 필요한 라인에만 f-string(f"...")을 적용하여 안전하게 결합합니다.
    return (
        "당신은 공식 문서 분석가이자 Neo4j 지식 그래프 아키텍트입니다.\n"
        f"아래 문서 청크({framework}, {lang})를 분석하여 핵심 기술 및 보안 개념을 Neo4j 그래프로 "
        "적재할 수 있는 JSON 배열로만 응답하라.\n\n"
        "## Neo4j 그래프 매핑 — 필드별 노드·엣지 생성 규칙 (4레이어 아키텍처)\n\n"
        "각 JSON 항목은 단일 마스터 Concept 노드로 MERGE된다. 'concept_name'이 병합 기준 키이다.\n\n"
        '  "concept_name"  →  MERGE (c:Concept {name: concept_name})\n'
        "      + APOC addLabels: domains 배열의 각 값 capitalize → 물리 다중 라벨 동적 누적\n"
        '        예) domains=["security","performance"] → :Concept:Security:Performance\n'
        "      ★ 동일 개념이 여러 문서에 등장해도 단일 노드로 수렴. 영문 표준 파스칼케이스 엄수 (예: XSS, SQLi, MemoryLeak)\n\n"
        '  "aliases"  →  노드 내부 속성 배열로 저장. 입구 단에서 중복 노드를 병합(Deduplication)시키는 데 사용됨.\n'
        "      → 공식 명칭·약어·별칭·한국어 번역명 모두 포함 (SAME_AS 관계선은 절대 생성하지 않음)\n\n"
        '  "security_mechanism"  →  MERGE (m:Mechanism {name: mechanism_name})\n'
        "      (c)-[:MITIGATED_BY]->(m)\n"
        '      → 완전 소문자 스네이크케이스 강제 (예: "output_encoding", "parameterized_query")\n\n'
        '  "affected_components"  →  MERGE (x:Component {name: each})\n'
        "      (c)-[:AFFECTS]->(x)\n"
        '      → 소문자 스네이크케이스 강제 (예: "template_rendering_layer", "heap_memory")\n\n'
        '  "root_cause"  →  MERGE (r:RootCause {name: root_cause})\n'
        "      (c)-[:CAUSED_BY]->(r)\n"
        "      → 소문자 스네이크케이스의 단일 문자열로 작성 (배열 반환 금지)\n\n"
        '  "config_properties"  →  MERGE (p:Property {unq_key: key}) SET p.value, p.type\n'
        "      (c)-[:TUNED_BY]->(p)\n"
        '      → 반드시 {"key": str, "value": str, "type": "security"|"tuning"} 형식 준수. 키는 소문자 스네이크케이스.\n\n'
        '  "code_examples"  →  MERGE (e:CodeExample {unq_id: 부모명_언어_프레임워크_버전...})\n'
        "      (m)-[:HAS_EXAMPLE]->(e)\n"
        '      → security_mechanism 내부에 중첩. {"lang": str, "lang_version": str, "framework": str, "framework_version": str, "code": str, "description": str} 형식\n\n'
        "## 필수 출력 JSON 스키마\n\n"
        "[\n"
        "  {\n"
        '    "concept_name": "영문_표준_파스칼케이스_식별자",\n'
        '    "concept_type": "vulnerability_root_cause" | "performance_antipattern",\n'
        '    "cwe_id": "CWE-번호 (없으면 null)",\n'
        '    "owasp_id": "A0x:2025 (없으 면 null)",\n'
        '    "severity": "critical"|"high"|"medium"|"low",\n'
        f'    "domains": [{domain_values} 중 1개 이상 (교차 도메인 시 복수 포함)],\n'
        '    "description_ko": "한국어 개념 요약 설명 (1~3문장)",\n'
        '    "aliases": ["동의어", "한글 번역명", "약어"],\n'
        '    "root_cause": "원인_스네이크_케이스",\n'
        '    "affected_components": ["컴포넌트_스네이크_케이스"],\n'
        '    "security_mechanism": [\n'
        '      {\n'
        '        "mechanism_name": "메커니즘_스네이크_케이스",\n'
        '        "code_examples": [\n'
        '          {"lang": "...", "lang_version": "...", "framework": "...", "framework_version": "...", "code": "...", "description": "..."}\n'
        '        ]\n'
        '      }\n'
        '    ],\n'
        '    "config_properties": [\n'
        '      {"key": "설정키_스네이크_케이스", "value": "값", "type": "security"|"tuning"}\n'
        '    ]\n'
        "  }\n"
        "]\n\n"
        "출력: 위 JSON 형식의 배열만 반환하라. (```json``` 마크다운 블록 허용, 설명 텍스트 금지)\n\n"
        f"---\n{text_chunk}\n---"
    )