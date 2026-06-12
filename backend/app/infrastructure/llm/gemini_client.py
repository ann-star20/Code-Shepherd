"""GeminiClient — PROD 모드 실제 Gemini API 호출. PRD §16.4."""

from __future__ import annotations

import json
import logging
import re

from app.domain.models import ConceptExtractionSchema
from app.infrastructure.llm.interface import ILLMClient

logger = logging.getLogger(__name__)


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

    def __init__(
        self, api_key: str, model: str = "gemini-2.5-flash", langsmith_project: str = ""
    ) -> None:
        try:
            from google import genai
            from google.genai import types
            from langsmith import traceable  # noqa: F401

            self._client = genai.Client(api_key=api_key)
            self._types = types
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
            model=self._model_name,
            contents=prompt,
            config=self._types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json",
            ),
        )

        self.raw_responses.append(response.text)
        logger.info("[RESPONSE RAW]\n%s", response.text)

        raw_list = _parse_json_safely(response.text)
        if not raw_list:
            logger.warning(
                "[EMPTY] doc_id=%s framework=%s lang=%s domains=%s chunk_len=%d",
                doc_id,
                metadata.get("framework", "Unknown"),
                metadata.get("lang", "EN"),
                domains_used,
                len(text_chunk),
            )
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
    """Extractor 프롬프트 빌더 — 온톨로지 핵심 규칙 및 데이터 유연성 완전 교정본."""
    framework = metadata.get("framework", "Unknown")
    lang = metadata.get("lang", "EN")
    domains = allowed_domains if allowed_domains else ["security", "performance"]
    domain_values = ", ".join(f'"{d}"' for d in domains)

    # 주의: JSON 스키마 부분의 중괄호({}) 충돌을 막기 위해,
    # 변수 바인딩이 필요한 라인에만 f-string(f"...")을 적용하여 안전하게 결합합니다.
    return (
        "당신은 공식 문서 분석가이자 Neo4j 지식 그래프 아키텍트입니다.\n"
        f"아래 문서 청크(대상 환경: {framework}, {lang})를 분석하여 핵심 기술 및 보안 개념을 완벽한 온톨로지 위계에 맞춰 "
        "적재할 수 있는 JSON 배열로만 응답하라. 스키마에 명시되지 않은 필드는 임의로 창작하거나 변형할 수 없다.\n\n"
        "## Neo4j 그래프 매핑 — 온톨로지 계층 및 다중 라벨 생성 헌법\n\n"
        "1. [Concept 노드 축]: 'concept_name'이 병합 기준 마스터 키이다. 기술적 이론, 메커니즘의 상위 추상 개념, 취약점 유형 등 '순수 개념' 명칭이어야 한다.\n"
        "   ★ 절대 'NestJS', 'Django', 'Spring' 같은 프레임워크/언어 명칭을 concept_name으로 잡지 말 것. (그것들은 하위 속성이자 격리 기준임)\n"
        "   ★ 올바른 예시: CSRF, XSS, SQLi, RateLimiting, ConnectionPooling, MemoryLeak\n"
        "   → MERGE (c:Concept {name: concept_name})\n"
        f"   → [🎯 물리 다중 라벨 처리]: 제공된 domains 배열({domain_values})의 각 값들을 Capitalize하여 물리 다중 라벨로 동적 누적 처리함.\n"
        '     예) domains=["security", "performance"] ➔ (:Concept:Security:Performance) 형태로 다중 라벨 바인딩.\n\n'
        "2. [aliases — 입력단 중복 제거용 영문/국문 동의어 풀]:\n"
        "   → 해당 개념의 영문 Full Name, 영문 파스칼케이스(PascalCase), 한글 번역명, 축약어, 이명(Synonym)을 모두 포함하는 플랫 배열.\n"
        '     예시: ["Cross-Site Request Forgery", "CrossSiteRequestForgery", "사이트간요청위조", "CSRF"]\n\n'
        "3. [Mechanism 노드 축 — 🎯 다중 언어/프레임워크 격리 가드레일]:\n"
        "   → MERGE (m:Mechanism {name: mechanism_name, lang: lang, framework: framework})\n"
        "   → 릴레이션 가교선: (c)-[:HAS_MECHANISM]->(m)\n"
        "   ★ 중요: 언어와 프레임워크 조합이 다르면 물리적으로 완벽히 '별개의 Mechanism 노드'가 생성되도록 복합 키 문맥을 형성함.\n"
        '   → 명칭은 완전 소문자 스네이크케이스 강제 (예: "requires_csrf_token_decorator", "csurf_middleware")\n\n'
        "4. [CodeExample 노드 축 — 메커니즘 하위 위계 종속]:\n"
        "   → MERGE (e:CodeExample {mechanism_id: id(m), lang: lang, framework: framework})\n"
        "   → 릴레이션 가교선: (m)-[:HAS_EXAMPLE]->(e)\n"
        "   ★ 절대 Concept에서 직접 [:HAS_EXAMPLE]로 조인하지 말 것. 반드시 Mechanism 노드를 허브 삼아 가교선을 전개하라.\n"
        "   → 실제 동작 가능한 현실적인 코드(`\\n` 개행 직렬화 포함)와 문맥(description)을 정밀 추출할 것.\n\n"
        "5. [기타 서브 레이어 규격]:\n"
        "   → Affected Components: MERGE (x:Component {name: each}) ➔ (c)-[:AFFECTS]->(x) (소문자 스네이크케이스)\n"
        "   → Root Cause: MERGE (r:RootCause {name: root_cause}) ➔ (c)-[:CAUSED_BY]->(r) (소문자 스네이크케이스 단일 문자열)\n"
        "   → Config Properties: MERGE (p:Property {unq_key: key}) SET p.value, p.type ➔ (c)-[:TUNED_BY]->(p)\n\n"
        "## 필수 출력 JSON 스키마 명세 (정밀 싱크 강제)\n"
        "※ 문서 내용에 해당하는 정보가 없거나 유추할 수 없는 메타 필드(cwe_id, severity 등)는 누락시키지 말고 반드시 'null' 또는 빈 배열('[]')로 명시하여 구조의 뼈대를 고수하라.\n\n"
        "[\n"
        "  {\n"
        '    "concept_name": "영문_표준_파스칼케이스_식별자",\n'
        '    "concept_type": "개념_유형_식별자 (vulnerability_root_cause, performance_antipattern 외에 도메인 맥락에 맞춰 추가 정의 및 확장 가능)",\n'
        '    "cwe_id": "CWE-번호 (없으면 null)",\n'
        '    "owasp_id": "A0x:2025 명세 (없으면 null)",\n'
        '    "severity": "critical"|"high"|"medium"|"low" (없으면 null),\n'
        f'    "domains": [{domain_values} 중 개념에 해당하는 도메인을 1개 이상 동적 선택],\n'
        '    "description_ko": "한국어 개념 요약 설명 (1~3문장)",\n'
        '    "aliases": ["영문 Full Name", "영문 PascalCase", "한글 번역명", "약어"],\n'
        '    "root_cause": "원인_스네이크_케이스 (없으면 null)",\n'
        '    "affected_components": ["컴포넌트_스네이크_케이스_배열", 없으면 빈 배열 []],\n'
        '    "mechanism": [\n'
        "      {\n"
        '        "mechanism_name": "메커니즘_스네이크_케이스",\n'
        '        "code_examples": [\n'
        "          {\n"
        '            "lang": "소문자 언어명",\n'
        '            "lang_version": "버전 명세 (없으면 null)",\n'
        '            "framework": "프레임워크명",\n'
        '            "framework_version": "버전 명세 (없으면 null)",\n'
        '            "code": "실제 소스코드 본문",\n'
        '            "description": "코드 문맥 및 의미론적 보호 기전 설명"\n'
        "          }\n"
        "        ]\n"
        "      }\n"
        "    ],\n"
        '    "config_properties": [\n'
        '      {"key": "설정키_스네이크_케이스", "value": "값", "type": "security"|"tuning"}\n'
        "    ] (없으면 빈 배열 [])\n"
        "  }\n"
        "]\n\n"
        "출력 가드레일: 마크다운 래핑 기호 ```json ``` 외에 어떤 서두 문구나 부연 설명 텍스트도 노출하지 말 것. 규정되지 않은 'security_mechanism' 등 임의의 키 생성을 엄격히 금지함. 순수한 JSON 데이터 구조만 반환하라.\n\n"
        f"---\n{text_chunk}\n---"
    )
