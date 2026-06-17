"""
Stage 5: 메타데이터 추출 Agent (trc_0005)

Gemini 2.5 Flash를 사용해 문서에서 구조화된 메타데이터와 Neo4j 엔티티를 추출한다.

출력:
    state["metadata"]        DocumentMetadata
    state["neo4j_entities"]  Neo4j에 저장할 Entity 목록
    state["neo4j_relations"] Chunk-Entity MENTIONS 관계 목록
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.pipeline.models import DocPipelineState, DocumentMetadata

logger = logging.getLogger(__name__)

from langchain_core.messages import HumanMessage, SystemMessage

from app.pipeline._gemini import call_gemini_quality, parse_gemini_json

import app.pipeline._category_definitions as _cat_defs
from app.pipeline._category_definitions import build_category_prompt_snippet

_SYSTEM_PROMPT = f"""\
당신은 사내 기술 문서 메타데이터 추출 에이전트입니다.
Markdown 형식의 기술 문서에서 구조화된 메타데이터와 핵심 엔티티를 추출하는 것이 유일한 임무입니다.

출력 형식 규칙 (절대 준수):
- 응답은 반드시 순수 JSON 객체여야 합니다.
- 코드 블록(```), 설명 텍스트, 마크다운 형식을 일절 포함하지 않습니다.

필드 제약 조건:
- category: 아래 기존 카테고리 목록에서 반드시 선택하세요.
  기존 카테고리로 충분히 분류 가능한 경우 새 카테고리명을 제안하지 마세요.
  기존 카테고리 중 어느 것으로도 전혀 설명할 수 없는 완전히 새로운 주제인 경우에만 새 이름을 사용하세요.
- category_reasoning: 카테고리를 선택한 근거를 2~3문장으로 설명하세요.
- category_alternatives: 기존 카테고리 중 차선책 1~2개를 배열로 제시하세요.
- team, author: 문서에 명시된 경우만 추출, 불명확하면 null
- entities[].type: "Technology", "Pattern", "Concept" 중 정확히 하나
  각 타입의 범위:
  - Technology: 기술 스택, 도구(tool), 제품(product), 표준(standard), API 엔드포인트(endpoint)
  - Pattern: 방법론(methodology), 프로세스(process), 절차, 아키텍처 패턴
  - Concept: 기술 개념, 역할(role) — 예: DevOps, 팀장, CDO, HR,
              조직/단체(organization) — 예: OpenAI, Google, 팀 이름, 회사명,
              지표(metric) — 예: 테스트 커버리지 82%, P95 응답 시간
- entities[].name: 원문 표기 그대로 유지 (대소문자·언어 변환 금지)

기존 카테고리 참고 (새 카테고리 제안 시 alternatives 에 활용):
{build_category_prompt_snippet()}

추출 원칙:
- 문서에 명시되지 않은 정보는 추측하지 않습니다.
- 제목은 문서 최상위 헤딩(#)을 우선하고, 없으면 내용을 요약합니다.
- 엔티티는 Technology(기술·도구·엔드포인트), Pattern(방법론·프로세스),
  Concept(개념·역할·조직·지표) 세 타입으로 분류하여 실질적으로 등장하는 것만 추출합니다.\
"""

_METADATA_PROMPT = f"""\
아래 기술 문서에서 메타데이터와 핵심 엔티티를 추출해주세요.

태그 작성 기준:
- 7~8개의 구체적인 태그를 생성하세요.
- 문서가 한국어로 작성된 경우 한국어 태그를 우선하되, 고유명사(제품명·브랜드명·약어)는 원어 표기를 유지하세요.
  예) 한국어 문서: ["트랜스포머", "자연어처리", "사전학습", "GPT", "LLM", "RLHF", "Attention", "임베딩"]
- 태그는 문서 핵심 기술, 도구, 방법론, 주요 개념을 균형 있게 포함하세요.

엔티티 추출 기준:
- Technology: 기술 스택, 도구, 제품, 표준, API 엔드포인트 — 예: pgvector, Docker, /api/v1/users
- Pattern: 방법론, 프로세스, 절차 — 예: TDD, 카나리 배포, Contract First
- Concept: 기술 개념 + 역할(Role) + 조직/단체(Organization) + 지표(Metric)
  예 (역할): DevOps, CDO, 팀장, HR, CISO
  예 (조직): OpenAI, Google, Anthropic, 네이버, LG헬로비전
  예 (지표): 테스트 커버리지 82%, P95 응답 시간, Precision@5

다음 JSON 형식으로만 응답하세요 (다른 텍스트 포함 금지):
{{{{
  "title": "문서 제목",
  "category": "가장 적합한 카테고리 (기존 또는 새로운 이름)",
  "category_reasoning": "이 카테고리를 선택한 이유 2~3문장",
  "category_alternatives": ["기존 카테고리 중 차선책1", "차선책2"],
  "team": "팀 이름 또는 null",
  "author": "작성자 또는 null",
  "tags": ["태그1", "태그2", "태그3", "태그4", "태그5", "태그6", "태그7"],
  "entities": [
    {{{{
      "name": "엔티티 이름",
      "type": "Technology | Pattern | Concept",
      "description": "한 줄 설명"
    }}}},
    {{{{
      "name": "팀장",
      "type": "Concept",
      "description": "역할 — 문서 관리·승인 담당자"
    }}}},
    {{{{
      "name": "OpenAI",
      "type": "Concept",
      "description": "조직 — GPT 모델 개발사"
    }}}}
  ]
}}}}

--- 문서 ---
{{markdown}}
"""


async def stage5_metadata(state: "DocPipelineState") -> dict:
    """LangGraph 노드: 메타데이터 + Neo4j 엔티티 추출."""

    markdown = state.get("validated_markdown") or ""
    doc_id = state["doc_id"]
    chunks = state.get("chunks") or []

    if not markdown:
        logger.error("Stage 5: validated_markdown 없음", extra={"doc_id": doc_id})
        return {
            "metadata": None,
            "neo4j_entities": [],
            "neo4j_relations": [],
            "status": "failed",
            "error": "Stage5: validated_markdown 없음",
            "current_stage": "stage5_metadata",
            "stage5_latency_ms": 0,
        }

    t0 = time.perf_counter()
    metadata, entities = await _extract_metadata(markdown, doc_id)
    stage5_latency_ms = int((time.perf_counter() - t0) * 1000)
    relations = _build_relations(chunks, entities)

    logger.info(
        "Stage 5 완료",
        extra={
            "doc_id": doc_id,
            "category": metadata.get("category"),
            "entity_count": len(entities),
        },
    )

    raw_category = metadata.get("category", "기타")
    reasoning = metadata.pop("category_reasoning", "")
    alternatives = metadata.pop("category_alternatives", [])

    category = _disambiguate_category(
        llm_category=raw_category,
        title=metadata.get("title", ""),
        tags=metadata.get("tags", []),
        markdown=markdown,
    )
    metadata["category"] = category
    is_new = category not in _cat_defs.VALID_CATEGORIES

    return {
        "metadata": metadata,
        "neo4j_entities": entities,
        "neo4j_relations": relations,
        "current_stage": "stage5_metadata",
        "category_reasoning": reasoning,
        "category_is_new": is_new,
        "category_alternatives": alternatives,
        "stage5_latency_ms": stage5_latency_ms,
    }


async def _extract_metadata(
    markdown: str, doc_id: str
) -> tuple["DocumentMetadata", list[dict]]:
    if os.getenv("USE_MOCK_LLM", "false").lower() == "true":
        return _mock_metadata(markdown), []

    sample = markdown[:4000] if len(markdown) > 4000 else markdown

    try:
        response = await call_gemini_quality([
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=_METADATA_PROMPT.format(markdown=sample)),
        ])
        data = parse_gemini_json(response.content)
    except json.JSONDecodeError as e:
        logger.error(
            "Stage 5: JSON 파싱 실패",
            extra={"doc_id": doc_id, "error": str(e)},
        )
        return _fallback_metadata(), []
    except Exception as e:
        logger.error(
            "Stage 5: Gemini API 실패",
            extra={"doc_id": doc_id, "error": str(e)},
        )
        return _fallback_metadata(), []

    ai_tags: list[str] = data.get("tags", [])
    merged_tags = list(dict.fromkeys(ai_tags))  # 중복 제거

    h1_title = _extract_h1_title(sample)
    metadata: "DocumentMetadata" = {
        "title": h1_title or data.get("title", "제목 없음"),
        "category": data.get("category", "기타"),
        "category_reasoning": data.get("category_reasoning", ""),
        "category_alternatives": data.get("category_alternatives", []),
        "team": data.get("team"),
        "author": data.get("author"),
        "tags": merged_tags,
        "source": "upload",
    }
    entities: list[dict] = data.get("entities", [])
    return metadata, entities


def _extract_heading_tags(markdown: str) -> list[str]:
    """마크다운의 #~### 헤딩을 순서대로 추출해 태그 목록으로 반환.

    H1은 보통 문서 제목이므로 title과 중복되더라도 태그에 포함.
    코드 블록(```) 안의 헤딩은 제외한다.
    """
    tags: list[str] = []
    in_code_block = False
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        m = re.match(r"^#{1,3}\s+(.+)$", stripped)
        if m:
            heading = m.group(1).strip()
            if heading and heading not in tags:
                tags.append(heading)
    return tags


def _build_relations(chunks: list[dict], entities: list[dict]) -> list[dict]:
    """
    Child 청크와 엔티티 사이의 MENTIONS 관계를 생성.
    엔티티 이름이 청크 내용에 포함되는 경우에만 연결한다.
    entity_name은 Neo4j에 저장된 원본 대소문자 그대로 사용한다.
    """
    relations = []
    # (소문자 검색용, 원본 이름) 쌍으로 유지
    entity_pairs = [(e["name"].lower(), e["name"]) for e in entities if e.get("name")]

    for chunk in chunks:
        if chunk["chunk_type"] != "child":
            continue
        content_lower = chunk["content"].lower()
        for name_lower, name_original in entity_pairs:
            if name_lower in content_lower:
                relations.append(
                    {
                        "from_chunk_id": chunk["chunk_id"],
                        "entity_name": name_original,
                        "relation_type": "MENTIONS",
                    }
                )
    return relations


def _fallback_metadata() -> "DocumentMetadata":
    return {
        "title": "제목 없음",
        "category": "기타",
        "category_reasoning": "",
        "category_alternatives": [],
        "team": None,
        "author": None,
        "tags": [],
        "source": "upload",
    }


_TITLE_SUFFIX_PATTERNS = re.compile(
    r"\s+(샘플\s*문서|초안|개정판|임시|테스트\s*문서|draft|temp|sample\s*doc)$",
    re.IGNORECASE,
)


def _clean_document_title(title: str) -> str:
    """제목 끝의 문서 상태 접미사(샘플 문서, 초안, 개정판 등)를 제거한다."""
    return _TITLE_SUFFIX_PATTERNS.sub("", title).strip()


def _extract_h1_title(markdown: str, max_lines: int = 10) -> str | None:
    """markdown에서 첫 번째 H1(# 제목)을 추출한다.

    max_lines 이내에 H1이 없으면 None을 반환한다.
    DOCX/PDF 변환 마크다운은 문서 제목이 일반 텍스트로 오고 챕터 헤딩이 H1으로
    나오는 경우가 있어서, 초반부에서만 H1을 탐색한다.
    """
    for line in markdown.splitlines()[:max_lines]:
        stripped = line.strip()
        if stripped.startswith("# ") or stripped == "#":
            title = stripped.lstrip("#").strip()
            return _clean_document_title(title) if title else None
    return None


# 제목에 이 키워드가 포함되면 AI_ML 카테고리로 교정한다.
# 제목(title)만 체크 — 본문/태그에 우연히 등장하는 키워드로 인한 오분류 방지.
_AI_ML_TITLE_KEYWORDS: list[str] = [
    # RAG
    "rag", "retrieval-augmented", "retrieval augmented",
    # 검색 품질 지표
    "sqm", "검색 품질 지표", "검색 품질 평가", "검색 랭킹 품질",
    "ndcg", "precision@", "recall@", "search quality metrics",
    # 임베딩
    "임베딩 파이프라인", "임베딩 설계", "임베딩 시스템",
    # ML 학습·배포
    "mlops", "파인튜닝", "fine-tuning",
    "llm 파이프라인", "ml 파이프라인",
]


def _disambiguate_category(
    llm_category: str,
    title: str,
    tags: list[str],
    markdown: str,
) -> str:
    """
    LLM이 반환한 카테고리가 부정확할 때 문서 제목 기반으로 교정한다.

    제목만 체크하는 이유: 태그·본문의 기술 용어(pgvector, 벡터 등)는
    AI_ML 문서가 아닌 장애 보고서·아키텍처 문서에도 등장할 수 있어
    과도한 AI_ML 오분류를 유발한다.

    적용 규칙:
    1. 제목에 AI_ML 시그널 키워드 → AI_ML 교정 (단, 이미 AI_ML이면 유지)
    2. llm_category 가 VALID_CATEGORIES 에 없으면 '기타'로 폴백
    3. 그 외 llm_category 그대로 반환
    """
    title_lower = title.lower()
    has_ai_ml_signal = any(kw in title_lower for kw in _AI_ML_TITLE_KEYWORDS)

    if has_ai_ml_signal and llm_category != "AI_ML":
        logger.info(
            "Stage 5: 카테고리 교정 AI_ML (제목 시그널)",
            extra={"from": llm_category, "title": title},
        )
        return "AI_ML"

    if llm_category not in _cat_defs.VALID_CATEGORIES:
        logger.warning(
            "Stage 5: 유효하지 않은 카테고리 → '기타' 폴백",
            extra={"category": llm_category, "title": title},
        )
        return "기타"

    return llm_category


def _mock_metadata(markdown: str) -> "DocumentMetadata":
    title = _extract_h1_title(markdown) or "제목 없음"
    return {
        "title": title,
        "category": "코딩컨벤션",   # Mock은 기존 카테고리 반환 → category_is_new=False
        "category_reasoning": "Mock LLM — 코딩컨벤션 카테고리로 기본 반환",
        "category_alternatives": ["아키텍처"],
        "team": None,
        "author": None,
        "tags": [],
        "source": "upload",
    }
