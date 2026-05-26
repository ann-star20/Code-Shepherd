from pydantic import BaseModel
from typing import Literal, Optional, TypedDict

# ── 팀 공통 State (CLAUDE.md §11) ──────────────────────────────────────────
# 실제 통합 시: from common.state import PRReviewState
# 개발 단계(Week 2~3): 아래 인라인 정의로 대체 — 필드 구조 동일해야 함
class PRReviewState(TypedDict, total=False):
    # Dev1이 채움 (입력)
    task_id: str
    pr_id: str
    pr_diff: str
    developer_id: str
    skill_level: Literal["junior", "mid", "senior"]
    tech_stack: list[str]
    architecture_docs: list[str]        # chunk_id 목록 (pgVector 검색 결과)
    coding_conventions: str
    previous_pr_issues: list[str]
    # Dev2/3가 채움
    analysis_results: list[dict]
    # Dev4가 채움
    verdict: Optional[Literal["lgtm", "rework", "escalate"]]
    comment_body: Optional[str]
    learning_resources: Optional[list[dict]]
    # Dev5가 채움
    issue_patterns: Optional[list[str]]
    curriculum_update: Optional[dict]


# ── Dev2 전용 추가 필드 (PRReviewState 확장) ─────────────────────────────────
class Dev2State(PRReviewState, total=False):
    """
    Dev2 내부 처리 State.
    PRReviewState 필드를 모두 상속하며, Dev2 파이프라인 전용 필드를 추가한다.
    통합(Week 5) 시 common.state.PRReviewState 임포트로 교체.
    """
    static_raw: list[dict]      # CLI 도구 원본 결과 (run_tools 노드 출력)
    security_raw: list[dict]    # 보안 도구 원본 결과 (run_tools 노드 출력)
    enriched: list[dict]        # pgVector 유사 이슈 + LLM 판단 결과
    final_output: list[dict]    # Output Contract A 형식 최종 결과


# ── Pydantic 모델 (Dev1 → Dev2 입력 계약 검증, CLAUDE.md §5-B) ─────────────
class Developer(BaseModel):
    id: str
    skill_level: Literal["junior", "mid", "senior"]
    tech_stack: list[str]


class TaskContext(BaseModel):
    """CLAUDE.md §5-B: Dev1 → Dev2/3 입력 계약의 context 필드"""
    architecture_docs: list[str] = []       # chunk_id 목록
    coding_conventions: str = ""
    previous_pr_issues: list[str] = []


class TaskPayload(BaseModel):
    """CLAUDE.md §5-B: Dev1 → Dev2/3 입력 계약 전체"""
    task_id: str
    pr_id: str
    pr_diff: str
    developer: Developer
    context: TaskContext = TaskContext()    # ← context 필드 추가 (팀 계약 준수)


class Issue(BaseModel):
    severity: Literal["Critical", "Major", "Minor"]
    issue_type: Literal["Bug", "Vulnerability", "Code Smell"] = "Bug"
    line: int
    file: str
    message: str
    rule_id: str
    suggestion: str
    resolution_example: str = ""    # 직관적인 숏코드 해결안 (예: "== None 말고 is None 써라")
    status: Literal["Open", "Accepted", "False Positive"] = "Open"
    similar_issues: list[dict] = []


class Summary(BaseModel):
    critical: int = 0
    major: int = 0
    minor: int = 0


class AgentOutput(BaseModel):
    """CLAUDE.md §5-A: Dev2/3 → Dev4 Output Contract"""
    agent: Literal["static_analysis", "security_scan"]
    task_id: str
    issues: list[Issue] = []
    summary: Summary = Summary()
    execution_ms: int
