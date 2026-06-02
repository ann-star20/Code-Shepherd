"""Dev3 에이전트 간 데이터 계약 — Pydantic v2 모델."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


class RepoInfo(BaseModel):
    clone_url: str
    commit_sha: str
    language: str = "python"
    test_command: str = "pytest --cov=src --cov-report=json"


class Developer(BaseModel):
    id: str
    skill_level: str = "junior"
    tech_stack: list[str] = []


class Dev3Context(BaseModel):
    developer: Developer
    previous_pr_issues: list[dict] = []


class Dev3Input(BaseModel):
    task_id: str
    scan_id: int
    pr_id: str
    pr_diff: str
    repo: RepoInfo
    developer: Developer


class Issue(BaseModel):
    severity: Literal["Critical", "Major", "Minor"]
    file: str
    line: Optional[int] = None
    message: str
    rule_id: str
    suggestion: str = ""
    keyword: str = ""        # 대분류 (고정 한글 라벨, Dev4 GROUP BY 통계 키) — §3.5
    sub_keyword: str = ""    # 세부 대상 (함수명·위치 등)
    metric_value: str = ""   # 수치 (있을 때만, 없으면 빈 문자열)


class SummaryCount(BaseModel):
    critical: int = 0
    major: int = 0
    minor: int = 0


class AgentOutput(BaseModel):
    task_id: str
    scan_id: int
    pr_id: str
    agent: Literal["test_verification", "performance"]
    issues: list[Issue] = []
    summary: SummaryCount = SummaryCount()
    metrics: Optional[dict] = None
    execution_ms: int = 0
