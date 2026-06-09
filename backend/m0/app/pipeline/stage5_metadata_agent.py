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
- entities[].name: 원문 표기 그대로 유지 (대소문자·언어 변환 금지)

기존 카테고리 참고 (새 카테고리 제안 시 alternatives 에 활용):
{build_category_prompt_snippet()}

추출 원칙:
- 문서에 명시되지 않은 정보는 추측하지 않습니다.
- 제목은 문서 최상위 헤딩(#)을 우선하고, 없으면 내용을 요약합니다.
- 엔티티는 실질적으로 등장하는 기술 도구, 패턴, 개념만 추출합니다.\
"""

_METADATA_PROMPT = f"""\
아래 기술 문서에서 메타데이터와 핵심 엔티티를 추출해주세요.

다음 JSON 형식으로만 응답하세요 (다른 텍스트 포함 금지):
{{{{
  "title": "문서 제목",
  "category": "가장 적합한 카테고리 (기존 또는 새로운 이름)",
  "category_reasoning": "이 카테고리를 선택한 이유 2~3문장",
  "category_alternatives": ["기존 카테고리 중 차선책1", "차선책2"],
  "team": "팀 이름 또는 null",
  "author": "작성자 또는 null",
  "tags": ["태그1", "태그2"],
  "entities": [
    {{{{
      "name": "엔티티 이름",
      "type": "Technology | Pattern | Concept",
      "description": "한 줄 설명"
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
        }

    metadata, entities = await _extract_metadata(markdown, doc_id)
    relations = _build_relations(chunks, entities)

    logger.info(
        "Stage 5 완료",
        extra={
            "doc_id": doc_id,
            "category": metadata.get("category"),
            "entity_count": len(entities),
        },
    )

    category = metadata.get("category", "기타")
    reasoning = metadata.pop("category_reasoning", "")
    alternatives = metadata.pop("category_alternatives", [])
    is_new = category not in _cat_defs.VALID_CATEGORIES

    return {
        "metadata": metadata,
        "neo4j_entities": entities,
        "neo4j_relations": relations,
        "current_stage": "stage5_metadata",
        "category_reasoning": reasoning,
        "category_is_new": is_new,
        "category_alternatives": alternatives,
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
            return title if title else None
    return None


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
