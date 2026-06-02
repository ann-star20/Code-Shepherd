"""AgentOutput 조립 — 이슈 목록 → severity 집계 → AgentOutput 반환."""
from __future__ import annotations

from typing import Optional

from contracts import AgentOutput, Issue, SummaryCount


def assemble_output(
    task_id: str,
    scan_id: int,
    pr_id: str,
    agent: str,
    issues: list[Issue],
    metrics: Optional[dict],
    execution_ms: int,
) -> AgentOutput:
    summary = SummaryCount(
        critical=sum(1 for i in issues if i.severity == "Critical"),
        major=sum(1 for i in issues if i.severity == "Major"),
        minor=sum(1 for i in issues if i.severity == "Minor"),
    )
    return AgentOutput(
        task_id=task_id,
        scan_id=scan_id,
        pr_id=pr_id,
        agent=agent,
        issues=issues,
        summary=summary,
        metrics=metrics,
        execution_ms=execution_ms,
    )
