"""⑤ compose_comment — findings 또는 gap → comment_md / gap_report

findings 경로: rule_id·§·source_path 인용 마크다운.
gap 경로: 지침공백 정직 보고 + 신규 지침 제안(GapReport.proposed_rule_md).
"""
from __future__ import annotations

import re
from collections import defaultdict

from contracts import Chunk, Finding, GapReport, ReviewState
from src.llm import call_llm

_GAP_SYSTEM = """\
당신은 사내 개발 가이드라인 작성자입니다. PR diff를 보고 아직 규정이 없는 패턴에 대해
신규 지침 초안을 작성합니다.

출력 형식 (순수 마크다운, 다른 텍스트 없이):
# [CONV-XXX-NNN] <규칙 제목>
- severity: Major | Minor | Info
- 배경: <도입 배경 1~2문장>

## §1 규칙
<규칙 본문>

## §2 올바른 예시
```python
<코드>
```

## §3 잘못된 예시
```python
<코드>
```
"""


def _severity_emoji(s: str) -> str:
    return {"Major": "🔴", "Minor": "🟡", "Info": "🔵"}.get(s, "⚪")


def _extract_location(f: Finding) -> str:
    """evidence_lines에서 함수명 추출. 없으면 file명 반환."""
    for line in f.evidence_lines:
        m = re.search(r"(?:async\s+)?def\s+(\w+)\s*\(", line.lstrip("+-").strip())
        if m:
            suffix = f" ({f.file})" if f.file else ""
            return f"`{m.group(1)}`{suffix}"
    return f"`{f.file}`" if f.file else ""


def compose_comment(state: ReviewState) -> dict:
    route: str = state.get("route", "proceed")
    findings: list[Finding] = state.get("findings", [])
    chunks: list[Chunk] = state.get("chunks", [])
    diff: str = state.get("diff", "")
    queries: list[str] = state.get("queries", [])

    if route == "gap_report":
        return _compose_gap(state, chunks, diff, queries)

    return _compose_findings(findings, chunks)


def _compose_findings(findings: list[Finding], chunks: list[Chunk]) -> dict:
    source_map: dict[str, str] = {c.rule_id: c.source_path for c in chunks}
    violations = [f for f in findings if f.verdict == "violation"]
    no_violations = [f for f in findings if f.verdict == "no_violation"]

    lines: list[str] = ["## 🔍 코드리뷰 에이전트 결과\n"]

    if not findings:
        lines.append("검토 결과 관련 사내 규칙을 찾지 못했습니다.\n")
        return {"comment_md": "\n".join(lines), "gap_report": None}

    if violations:
        # ISSUE-1: rule_id로 묶어 코멘트 1개 per rule
        grouped: dict[str, list[Finding]] = defaultdict(list)
        for f in violations:
            grouped[f.rule_id].append(f)

        lines.append(f"**위반 {len(violations)}건** 발견되었습니다.\n")

        for rule_id, group in grouped.items():
            first = group[0]
            lines.append(f"---\n### {_severity_emoji(first.severity)} [{rule_id}] {first.severity}")

            # 위반 위치 목록
            locations = [loc for f in group if (loc := _extract_location(f))]
            if locations:
                lines.append(f"**위반 위치**: {', '.join(locations)}")

            # ISSUE-2: URL 링크 대신 텍스트 출처
            source = source_map.get(rule_id, "")
            src_ref = f" (출처: {source})" if source else ""
            lines.append(f"\n**규칙 인용**{src_ref}:")
            lines.append(f"> {first.rule_quote}")

            # 위반별 코드 블록
            for f in group:
                if f.evidence_lines:
                    loc_label = _extract_location(f)
                    label = f" — {loc_label}" if loc_label else ""
                    lines.append(f"\n**위반 코드{label}**:")
                    lines.append("```")
                    lines.extend(f.evidence_lines)
                    lines.append("```")

            lines.append(f"\n**판단**: {first.reasoning}")
            fp_notes = [f.fp_note for f in group if f.fp_note]
            if fp_notes:
                lines.append(f"\n*오탐 검토*: {'; '.join(fp_notes)}")
    else:
        lines.append("위반 사항이 없습니다.\n")

    if no_violations:
        lines.append("\n<details><summary>준수 확인 규칙</summary>\n")
        for f in no_violations:
            lines.append(f"- [{f.rule_id}]: {f.reasoning}")
        lines.append("</details>")

    return {"comment_md": "\n".join(lines), "gap_report": None}


def _compose_gap(
    state: ReviewState,
    chunks: list[Chunk],
    diff: str,
    queries: list[str],
) -> dict:
    nearest_ids = list({c.rule_id for c in chunks[:3]})

    proposed = call_llm(
        "compose_comment",
        _GAP_SYSTEM,
        f"## 지침이 없는 패턴의 PR diff\n{diff[:1200]}",
    )

    pattern_summary = (
        "코퍼스에 관련 규칙 없음 — "
        + (diff.splitlines()[0].lstrip("+-").strip()[:80] if diff else "변경 패턴 불명")
    )

    gap = GapReport(
        pattern_summary=pattern_summary,
        queries_tried=queries,
        nearest_rule_ids=nearest_ids,
        proposed_rule_md=proposed.strip(),
    )

    comment = (
        "## ⚠️ 지침공백 보고\n\n"
        "이 PR의 변경 패턴에 해당하는 **사내 KMS 규칙을 찾지 못했습니다.**\n\n"
        f"**시도한 검색 질의**: {', '.join(queries)}\n\n"
        f"**가장 근접한 규칙**: {', '.join(nearest_ids) if nearest_ids else '없음'}\n\n"
        "---\n\n**신규 지침 제안 초안:**\n\n"
        + proposed.strip()
    )
    return {"comment_md": comment, "gap_report": gap}
