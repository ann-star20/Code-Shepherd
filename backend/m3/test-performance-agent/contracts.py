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
    sub_category: str = ""   # 표준 세부 유형 라벨 (탐지 항목만 고정 매핑, 없으면 빈 값) — Dev4
    code_context: str = ""   # 함수 한 줄 설명 (LLM, 성능 이슈만; 키 없으면 빈 값) — Dev4
    rag_context: str = ""    # 검색된 사내 가이드 (정성, 코멘트 인용용, 선택) — RAG §6
    # ── Dev2와 통일한 scan_issues 컬럼 ──
    github_id: str = ""              # PR 작성자 GitHub 아이디(문자) — developer.id
    code_snippet: str = ""           # 문제 함수 전체 소스 (AST=사실, 성능 이슈만)
    programming_language: str = ""   # "python" 등 (requirements 감지)
    framework: str = ""              # django/flask/fastapi 등 (requirements 파싱)
    framework_version: str = ""      # 프레임워크 핀 버전 (있을 때만)


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
