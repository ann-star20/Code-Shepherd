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
            import google.generativeai as genai
            from langsmith import traceable  # noqa: F401

            genai.configure(api_key=api_key)
            self._model = genai.GenerativeModel(model)
            logger.info("GeminiClient 초기화 — model: %s", model)
        except ImportError as exc:
            raise RuntimeError(
                "google-generativeai 또는 langsmith 패키지가 없습니다: pip install google-generativeai langsmith"
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

        response = await self._model.generate_content_async(prompt)

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
    domains = allowed_domains if allowed_domains else DEFAULT_DOMAINS
    domain_values = ", ".join(f'"{d}"' for d in domains)

    return (
        f"당신은 공식 문서 분석가이자 Neo4j 지식 그래프 아키텍트입니다.\n"
        f"아래 문서 청크({framework}, {lang})를 분석하여 핵심 개념을 Neo4j 그래프로 "
        "적재할 수 있는 JSON 배열로만 응답하라.\n\n"
        "## Neo4j 그래프 매핑 — 필드별 노드·엣지 생성 규칙\n\n"
        "각 JSON 항목은 Concept 노드 1개로 MERGE된다. concept_name이 MERGE 키이다.\n\n"
        '  "concept_name"  →  MERGE (c:Concept {name: concept_name})\n'
        "      + APOC addLabels: domains 배열의 각 값 capitalize → 물리 다중 라벨 누적\n"
        '        예) domains=["security","performance"] → :Concept:Security:Performance\n'
        "      ★ 동일 개념이 여러 문서에 등장해도 같은 이름이면 단일 노드로 병합\n"
        "        → 영문 표준 식별자 사용 (XSS, SQLi, CsrfViewMiddleware 등)\n\n"
        '  "aliases"  →  Link Resolver가 aliases 교집합으로 (c1)-[:SAME_AS]-(c2) 생성\n'
        "      → 공식 명칭·약어·별칭 모두 포함 (SAME_AS 탐색 정확도 결정)\n\n"
        '  "security_mechanism"  →  MERGE (m:SecurityMechanism {name: each})\n'
        "      (c)-[:MITIGATED_BY]->(m)\n"
        '      → 재사용 가능한 표준 명칭 (예: "CSRFToken", "SameSiteCookie", "RateLimit")\n\n'
        '  "affected_components"  →  MERGE (x:Component {name: each})\n'
        "      (c)-[:AFFECTS]->(x)\n"
        '      → 구체적 경로·컴포넌트명 (예: "django.middleware.csrf", "HTML 폼", "세션 쿠키")\n\n'
        '  "root_cause"  →  MERGE (r:RootCause {name: root_cause})\n'
        "      (c)-[:CAUSED_BY]->(r)\n"
        "      → 단일 문자열로 작성 (list 반환 금지)\n\n"
        '  "config_properties"  →  MERGE (p:ConfigProperty {key}) SET p.value\n'
        "      (c)-[:CONFIGURED_BY]->(p)\n"
        '      → 반드시 {"key": str, "value": str} 형식 준수\n\n'
        '  "code_examples"  →  MERGE (e:CodeExample {concept_name, lang, framework})\n'
        "      (c)-[:HAS_EXAMPLE]->(e)\n"
        '      → {"lang": str, "framework": str, "code": str} 형식\n\n'
        "## 스키마\n\n"
        "필수:\n"
        '  "concept_name": str  — 영문 표준 식별자 (MERGE 키, 문서 내 실제 개념만)\n'
        f'  "domains": list[str]  — 허용값: {domain_values}\n'
        '    교차 도메인 허용. "both" 사용 금지. 미등록 도메인은 그대로 포함.\n'
        '  "severity": "critical"|"high"|"medium"|"low"\n'
        '  "description_ko": str  — 한국어 설명 (1~3문장)\n\n'
        "선택:\n"
        '  "concept_type": "vulnerability_root_cause"|"security_mechanism"|"attack_vector"|"compliance_control"\n'
        '  "cwe_id": str,  "owasp_id": str\n'
        '  "aliases": list[str]\n'
        '  "security_mechanism": list[str]\n'
        '  "affected_components": list[str]\n'
        '  "config_properties": list[{"key": str, "value": str}]\n'
        '  "root_cause": str\n'
        '  "code_examples": list[{"lang": str, "framework": str, "code": str}]\n\n'
        "출력: JSON 배열만 반환 (```json``` 마크다운 허용, 설명 텍스트 금지)\n\n"
        f"---\n{text_chunk}\n---"
    )
