"""M2 + M3 AgentOutput 집계 → (combined_issues, verdict, summary)."""
from __future__ import annotations

from typing import Literal

from contracts import AgentOutput, CombinedIssue, SummaryCount
from config.settings import CRITICAL_ESCALATE_THRESHOLD, MAJOR_REWORK_THRESHOLD


def aggregate(
    outputs: list[AgentOutput],
) -> tuple[list[CombinedIssue], Literal["lgtm", "rework", "escalate"], SummaryCount]:
    """여러 AgentOutput을 하나로 합쳐 verdict를 판정한다.

    Args:
        outputs: M2(정적·보안) + M3(테스트·성능) AgentOutput 목록

    Returns:
        (combined_issues, verdict, summary) 3-튜플

    Raises:
        ValueError: 서로 다른 scan_id가 섞인 경우
    """
    if not outputs:
        return [], "lgtm", SummaryCount()

    # scan_id 일관성 검증
    scan_ids = {o.scan_id for o in outputs}
    if len(scan_ids) > 1:
        raise ValueError(f"scan_id 불일치 — 하나의 scan_id만 허용됩니다: {sorted(scan_ids)}")

    # (rule_id, file, line) 키로 중복 제거하며 이슈 수집
    seen: set[tuple[str, str, int | None]] = set()
    combined: list[CombinedIssue] = []
    for output in outputs:
        for issue in output.issues:
            key = (issue.rule_id, issue.file, issue.line)
            if key not in seen:
                seen.add(key)
                combined.append(
                    CombinedIssue(
                        severity=issue.severity,
                        file=issue.file,
                        line=issue.line,
                        message=issue.message,
                        rule_id=issue.rule_id,
                        suggestion=issue.suggestion,
                        source_agent=output.agent,
                        rag_context=issue.rag_context,  # 사내 가이드 전달 — RAG §6
                    )
                )

    # severity 카운트
    critical = sum(1 for i in combined if i.severity == "Critical")
    major = sum(1 for i in combined if i.severity == "Major")
    minor = sum(1 for i in combined if i.severity == "Minor")
    summary = SummaryCount(critical=critical, major=major, minor=minor)

    # verdict 판정 (Critical 우선)
    if critical >= CRITICAL_ESCALATE_THRESHOLD:
        verdict: Literal["lgtm", "rework", "escalate"] = "escalate"
    elif major >= MAJOR_REWORK_THRESHOLD:
        verdict = "rework"
    else:
        verdict = "lgtm"

    return combined, verdict, summary
