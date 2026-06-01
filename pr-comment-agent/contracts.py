"""pr-comment-agent 데이터 계약 — Pydantic v2."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, field_validator, model_validator

# ── Dev3 AgentOutput 미러 (test-performance-agent/contracts.py 동일 스키마) ──

class Issue(BaseModel):
    severity: Literal["Critical", "Major", "Minor"]
    file: str
    line: Optional[int] = None
    message: str
    rule_id: str
    suggestion: str = ""


class SummaryCount(BaseModel):
    critical: int = 0
    major: int = 0
    minor: int = 0


class AgentOutput(BaseModel):
    task_id: str
    scan_id: int
    pr_id: str
    agent: str  # "test_verification" | "performance" | "static_security" etc.
    issues: list[Issue] = []
    summary: SummaryCount = SummaryCount()
    metrics: Optional[dict] = None
    execution_ms: int = 0


class Developer(BaseModel):
    name: str = "unknown"
    skill_level: Literal["junior", "mid", "senior"] = "mid"

    @field_validator("skill_level")
    @classmethod
    def _validate_skill(cls, v: str) -> str:
        if v not in ("junior", "mid", "senior"):
            raise ValueError(f"skill_level must be junior/mid/senior, got {v!r}")
        return v


# ── pr-comment-agent 자체 모델 ──

Verdict = Literal["lgtm", "rework", "escalate"]


class CombinedIssue(BaseModel):
    severity: Literal["Critical", "Major", "Minor"]
    file: str
    line: Optional[int] = None
    message: str
    rule_id: str
    suggestion: str = ""
    source_agent: Optional[str] = None


class ReviewSummary(BaseModel):
    critical: int = 0
    major: int = 0
    minor: int = 0


class ReviewReport(BaseModel):
    verdict: Verdict
    summary: ReviewSummary = ReviewSummary()
    comment_md: str = ""
    escalation_needed: bool = False
    issues: list[CombinedIssue] = []
    gh_response: Optional[dict] = None

    @model_validator(mode="after")
    def _compute(self) -> "ReviewReport":
        if self.issues:
            self.summary = ReviewSummary(
                critical=sum(1 for i in self.issues if i.severity == "Critical"),
                major=sum(1 for i in self.issues if i.severity == "Major"),
                minor=sum(1 for i in self.issues if i.severity == "Minor"),
            )
        if self.verdict == "escalate":
            self.escalation_needed = True
        return self
