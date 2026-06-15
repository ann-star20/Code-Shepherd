"""④ judge — chunks, pr_context → findings[]

단일 CoT 프롬프트: [검사계획→조항-코드 대조→오탐 점검].
검증 불변 조건: rule_quote ⊂ Chunk.text, evidence_lines 각 줄 ⊂ diff (string-match).
"""
from __future__ import annotations

import json
import re

from contracts import Chunk, Finding, ReviewState
from src.config import MAX_JUDGE_CHUNKS
from src.llm import call_llm

# 모델이 스키마 외 값을 반환할 경우 정규화 (ValidationError 방지)
_VERDICT_MAP: dict[str, str] = {
    "pass": "no_violation",
    "no violation": "no_violation",
    "compliant": "no_violation",
    "ok": "no_violation",
    "fail": "violation",
    "violation_found": "violation",
}

_SYSTEM = """\
당신은 코드리뷰 에이전트입니다. 제공된 사내 KMS 규칙 코퍼스를 근거로 PR diff를 심사합니다.

## 검사 절차 (CoT 3단계)
1. 검사 계획: 각 규칙이 이 diff와 실질적으로 관련 있는지 판단한다. diff에 없는 패턴의 규칙은 건너뛴다.
2. 조항-코드 대조: 관련 규칙의 §금지 항목을 diff가 사용하는지 확인한다. 규칙의 §올바른 예시 패턴을 따르면 위반이 아니다.
3. 오탐 점검: 예외 조항(§4 등)·문맥을 확인한다.

## verdict 판단 기준 (엄격 준수)
- "violation": diff가 규칙의 금지 항목을 실제로 사용함.
- "no_violation": diff가 규칙의 권장 패턴을 따르거나, 규칙과 실질적으로 무관함.
- 규칙의 §올바른 예시 패턴(예: httpx.AsyncClient)을 그대로 사용하면 반드시 "no_violation".

## 출력 규칙
- findings: violation 건만 포함. 준수·무관 건은 포함하지 않는다.
- rule_quote: [규칙 코퍼스]에서 그대로 복사 (패러프레이즈 절대 금지).
- evidence_lines: [심사할 diff]에서 그대로 복사 (패러프레이즈 절대 금지).
- 위반 없으면 findings는 빈 배열.

## JSON 스키마 (순수 JSON만. 코드블록·서두·설명 없이):
{
  "findings": [
    {
      "rule_id": "CONV-XXX-NNN",
      "verdict": "violation",
      "severity": "Major",
      "rule_quote": "<코퍼스에서 그대로 복사>",
      "file": "<위반 파일 경로 또는 빈 문자열>",
      "evidence_lines": ["<diff에서 그대로 복사한 줄>"],
      "reasoning": "<§금지항목-코드 대조 1~3문장>",
      "fp_note": "<오탐 점검 메모 또는 null>"
    }
  ]
}
"""


def _parse_json(raw: str) -> dict:
    text = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\s*```\s*$", "", text)
    obj, _ = json.JSONDecoder().raw_decode(text.strip())
    return obj


def _normalize_verdict(v: str) -> str:
    return _VERDICT_MAP.get(v.lower().strip(), v)


def _format_chunks(chunks: list[Chunk]) -> str:
    parts = []
    for c in chunks:
        parts.append(f"### [{c.rule_id}] {c.section} (severity={c.severity}, source={c.source_path})")
        parts.append(c.text)
        parts.append("")
    return "\n".join(parts)


def judge(state: ReviewState) -> dict:
    chunks: list[Chunk] = state.get("chunks", [])
    diff: str = state.get("diff", "")

    seen: set[str] = set()
    deduped: list[Chunk] = []
    for c in chunks:
        key = f"{c.rule_id}_{c.section}"
        if key not in seen:
            seen.add(key)
            deduped.append(c)
    deduped = deduped[:MAX_JUDGE_CHUNKS]

    if not deduped:
        return {"findings": []}

    user_suffix = f"## 규칙 코퍼스\n{_format_chunks(deduped)}\n\n## 심사할 diff\n{diff}"
    raw = call_llm("judge", _SYSTEM, user_suffix)

    data = _parse_json(raw)
    findings = []
    for f in data.get("findings", []):
        f["verdict"] = _normalize_verdict(f.get("verdict", ""))
        findings.append(Finding(**f))
    return {"findings": findings}
