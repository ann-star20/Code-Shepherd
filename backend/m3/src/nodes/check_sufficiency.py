"""③ check_sufficiency — chunks, pr_context → Command(route)

D3: LLM relevance 판정 후 Command(goto=...) 3갈래.
  proceed    → judge (청크가 diff에 관련 있음)
  requery    → retrieve (관련 없음, 재질의 1회 상한 미달)
  gap_report → compose_comment (관련 없음, 재질의 소진)

Command 패턴: examples/langgraph_reference.py 예제 B 그대로.
"""
from __future__ import annotations

import json
import re
from typing import Literal

from langgraph.types import Command

from contracts import Chunk, ReviewState
from src.config import MAX_REQUERY, SYNONYMS_PER_CONCEPT
from src.llm import call_llm

_SYSTEM = """\
당신은 코드리뷰 에이전트입니다. 검색된 규칙 청크가 PR diff를 심사하기에 충분한지 판단합니다.

## sufficient=true 판단 기준 (넓게 해석)
다음 중 하나라도 해당하면 sufficient=true:
- diff에 규칙의 §금지 패턴(라이브러리, 함수, 구문 등)이 나타남
- diff에 규칙의 §올바른 예시 또는 §잘못된 예시에 등장하는 패턴이 나타남
- diff에 규칙의 예외 조항이 적용될 수 있는 패턴이 나타남
위반 여부나 예외 적용 여부는 judge가 판단한다. 여기서는 관련성만 판단한다.

## sufficient=false 판단 기준 (엄격하게)
모든 청크가 diff의 변경 내용과 완전히 무관한 다른 도메인의 규칙일 때만 false.

## 출력 (순수 JSON만):
{
  "sufficient": true,
  "reason": "<1문장 판단 근거>"
}
또는
{
  "sufficient": false,
  "reason": "<1문장>",
  "new_queries": ["<이전과 다른 검색 질의 1>", "<질의 2>", "<질의 3>"]
}

- new_queries: sufficient=false일 때만. 이전 질의와 다른 새 관점 3개.
- 순수 JSON만. 마크다운 코드블록 없이.
"""

_GAP_COMPOSE_SYSTEM = """\
당신은 사내 개발 가이드라인 작성자입니다. PR diff를 보고 아직 규정이 없는 패턴에 대해
신규 지침 초안을 작성합니다.

출력 형식 (순수 마크다운, JSON 아님):
# [CONV-XXX-NNN] <규칙 제목>
- severity: Major | Minor | Info
- 배경: <실제 또는 가상의 도입 배경 1~2문장>

## §1 규칙
<규칙 본문>

## §2 올바른 예시
```<언어>
<코드>
```

## §3 잘못된 예시
```<언어>
<코드>
```
"""


def _parse_json(raw: str) -> dict:
    text = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\s*```\s*$", "", text)
    obj, _ = json.JSONDecoder().raw_decode(text.strip())
    return obj


def check_sufficiency(
    state: ReviewState,
) -> Command[Literal["retrieve", "judge", "compose_comment"]]:
    chunks: list[Chunk] = state.get("chunks", [])
    diff: str = state.get("diff", "")
    queries: list[str] = state.get("queries", [])
    requery_count: int = state.get("requery_count", 0)

    # 청크 없으면 바로 분기 결정
    if not chunks:
        if requery_count < MAX_REQUERY:
            fallback = [f"{q} 관련 규칙" for q in queries[:SYNONYMS_PER_CONCEPT]]
            return Command(
                update={"queries": fallback, "requery_count": requery_count + 1, "route": "requery"},
                goto="retrieve",
            )
        return Command(update={"route": "gap_report"}, goto="compose_comment")

    chunk_summary = "\n".join(
        f"- [{c.rule_id}] {c.section}: {c.text[:120]}..." for c in chunks[:5]
    )
    user_suffix = (
        f"## 검색된 규칙 청크\n{chunk_summary}\n\n"
        f"## 심사 대상 diff (핵심 부분)\n{diff[:800]}"
    )
    raw = call_llm("check_sufficiency", _SYSTEM, user_suffix)
    data = _parse_json(raw)

    if data.get("sufficient"):
        return Command(update={"route": "proceed"}, goto="judge")

    if requery_count < MAX_REQUERY:
        new_queries: list[str] = data.get("new_queries") or [
            f"{q} 대체" for q in queries[:SYNONYMS_PER_CONCEPT]
        ]
        return Command(
            update={"queries": new_queries, "requery_count": requery_count + 1, "route": "requery"},
            goto="retrieve",
        )

    return Command(update={"route": "gap_report"}, goto="compose_comment")
