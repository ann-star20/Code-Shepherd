"""① extract_concepts — pr_context → concepts[{name, synonyms[3]}], queries[]

계약: contracts/README.md 표 ①. 동의어 수 기본 3 (src/config.py SYNONYMS_PER_CONCEPT).
"""
from __future__ import annotations

import json
import re

from contracts import Concept, ReviewState
from src.llm import call_llm


def _parse_json(raw: str) -> dict:
    """LLM 응답에서 첫 번째 JSON 객체만 추출 (후행 텍스트·이중 블록 무시)."""
    text = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\s*```\s*$", "", text)
    obj, _ = json.JSONDecoder().raw_decode(text.strip())
    return obj

_SYSTEM = """\
당신은 코드리뷰 에이전트입니다. PR diff를 분석해서 사내 KMS 규칙 검색에 쓸 개념과 검색 질의를 추출합니다.

출력은 순수 JSON만. 마크다운 코드블록·설명·서두 없이.

JSON 스키마:
{
  "concepts": [{"name": "string", "synonyms": ["string", "string", "string"]}],
  "queries": ["string", ...]
}

규칙:
- concepts: diff에서 감지된 개발 관습/패턴 1~5개. synonyms 정확히 3개.
- queries: 벡터 검색용 자연어 질의 3~8개. 한국어와 영어 모두 허용.
- 명시적으로 언급되지 않아도 관련 규칙이 있을 법한 맥락 패턴도 포함.
"""


def extract_concepts(state: ReviewState) -> dict:
    pr_context = state.get("pr_context", "")
    raw = call_llm("extract_concepts", _SYSTEM, f"## 분석할 PR 변경사항\n{pr_context}")

    data = _parse_json(raw)
    concepts = [Concept(**c) for c in data["concepts"]]
    queries: list[str] = data["queries"]
    return {"concepts": concepts, "queries": queries}
