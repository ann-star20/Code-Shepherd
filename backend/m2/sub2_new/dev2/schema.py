from pydantic import BaseModel
from typing import Any, Literal, Optional, TypedDict

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
    static_raw: list[dict]             # CLI 도구 원본 결과 (run_tools 노드 출력)
    security_raw: list[dict]           # 보안 도구 원본 결과 (run_tools 노드 출력)
    enriched: list[dict]               # pgVector 유사 이슈 + LLM 판단 결과
    final_output: list[dict]           # Output Contract A 형식 최종 결과
    tool_plan: Optional[dict]          # tool_router_agent 출력 (도구 선택 계획)
    action_decision: Optional[dict]    # action_decider_agent 출력 (후속 액션 추천)
    comment_body: str                  # LLM이 생성한 PR 코멘트 마크다운 (aggregate 파이프라인)
    github_comment_url: Optional[str]  # 등록된 GitHub 코멘트 URL (aggregate 파이프라인)


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


class LearningContext(BaseModel):
    """M4 학습자료 생성용 컨텍스트 — 프레임워크/언어/도메인 정보"""
    framework: str = "none"
    language: str = "python"
    domain_context: str = "ecommerce"


class CodeContext(BaseModel):
    """M4 개인화 학습 피드백용 — 이슈 라인 주변 코드 맥락.

    pr_diff / file / line / code_snippet 으로 규칙 기반 조립한다 (LLM 호출 없음).
    찾지 못하면 issue_line = code_snippet, 그것도 없으면 "snippet_unavailable".
    """
    context_before: list[str] = []      # 이슈 라인 앞 코드 (3~5줄)
    issue_line: str = ""                 # 문제가 발생한 코드 한 줄
    context_after: list[str] = []        # 이슈 라인 뒤 코드 (3~5줄)
    context_summary: str = ""            # 규칙 기반 맥락 설명 (빈 문자열 금지)


class IssueTaxonomy(BaseModel):
    """M4 개인화 학습 피드백용 — 보안/정적분석 기준 하위 분류.

    성능/테스트/함수 정밀 분석은 M3 담당이므로 제외한다.
    rule_id / mistake_type / 코드 패턴 기반으로 규칙 분류한다.
    """
    category: str = "General"            # 예: "Security", "Code Quality"
    subcategory: str = "Code Quality"    # 예: "Injection", "XSS"
    issue_type: str = "Unknown"          # 예: "SQL Injection"
    sub_issue_type: str = "General Review Issue"  # 예: "Raw Query String Formatting"


class Issue(BaseModel):
    # ── 기존 필드 (변경 없음) ────────────────────────────────────────────────────
    severity: Literal["Critical", "Major", "Minor"]
    issue_type: Literal["Bug", "Vulnerability", "Code Smell"] = "Bug"
    line: int
    file: str
    message: str
    rule_id: str
    suggestion: str
    resolution_example: str = ""
    status: Literal["Open", "Accepted", "False Positive"] = "Open"
    similar_issues: list[dict] = []
    # ── M4 매핑 필드 (신규, 모두 optional) ──────────────────────────────────────
    keyword: str = ""                        # 상위 보안 개념명. 예: "SQL Injection"
    sub_category: str = ""                   # 하위 실수 유형. 예: "raw_query"
    concept_id: str = ""                     # 그래프 DB Concept ID. 예: "sql_injection"
    mistake_type_concept_id: str = ""        # 하위 ID. 예: "sql_injection.raw_query"
    confidence_score: float = 0.0            # 분류 신뢰도 0.0~1.0
    code_snippet: str = ""                   # 문제 코드 조각 (없으면 "snippet_unavailable")
    name_of_function: str = ""               # 이슈 발생 라인을 감싸는 함수명 (함수 밖이면 "")
    learning_context: LearningContext = LearningContext()
    code_context: CodeContext = CodeContext()        # 이슈 라인 주변 코드 맥락 (M4 피드백용)
    taxonomy: IssueTaxonomy = IssueTaxonomy()         # 보안/정적분석 하위 분류 (M4 피드백용)


class ToolPlan(BaseModel):
    """tool_router_agent 출력 — run_tools가 실행할 도구 목록"""
    changed_files: list[str] = []
    detected_languages: list[str] = []
    risk_keywords: list[str] = []
    dependency_changed: bool = False
    selected_tools: list[str] = []
    llm_required: bool = True
    reason: list[str] = []


class ActionDecision(BaseModel):
    """action_decider_agent 출력 — M0/Dev4 참고용 후속 액션 추천"""
    recommended_action: Literal[
        "early_escalation", "request_rework", "needs_human_review", "store_only"
    ]
    reason: str
    confidence: float
    signals: dict[str, Any] = {}


class Summary(BaseModel):
    critical: int = 0
    major: int = 0
    minor: int = 0
    recommended_action: str = ""     # action_decider_agent 추천값 (M0/Dev4 참고용)


class AgentOutput(BaseModel):
    """CLAUDE.md §5-A: Dev2/3 → Dev4 Output Contract"""
    agent: Literal["static_analysis", "security_scan"]
    task_id: str
    issues: list[Issue] = []
    summary: Summary = Summary()
    execution_ms: int
    metadata: dict[str, Any] = {}   # action_decision 등 부가 정보


# ── 파이프라인 2 (취합 → 코멘트 → 알림) 계약 (CLAUDE.md §11, PRD 노드 I~O) ──────
class AggregatePayload(BaseModel):
    """POST /aggregate 입력 계약 (M0 → Dev2)

    M0(Orchestrator)가 M2+M3의 AgentOutput을 모아 전달한다.
    all_results: AgentOutput dict 리스트 (static_analysis, security_scan, ...).
    """
    task_id: str
    pr_id: str
    developer: Developer
    context: TaskContext = TaskContext()
    all_results: list[dict] = []    # AgentOutput × N (M2×2 + M3×2)


class AggregateState(TypedDict, total=False):
    """파이프라인 2 내부 처리 State.

    흐름: aggregate → comment_refine → github_comment → [Critical?] → slack_notify
    Dev2State와 별개 — M2+M3 취합 결과를 받아 코멘트/알림까지 담당한다.
    """
    # ── 입력 (M0가 채움) ──────────────────────────────────────────────────────
    task_id: str
    pr_id: str
    developer_id: str
    skill_level: Literal["junior", "mid", "senior"]
    tech_stack: list[str]
    architecture_docs: list[str]
    coding_conventions: str
    previous_pr_issues: list[str]
    all_results: list[dict]
    # ── aggregate_node 출력 ──────────────────────────────────────────────────
    aggregated_issues: list[dict]      # severity 정렬된 전체 이슈
    total_summary: dict                # {"critical": n, "major": n, "minor": n}
    # ── comment_refine_node 출력 ─────────────────────────────────────────────
    comment_body: str                  # LLM이 생성한 PR 코멘트 마크다운
    # ── github_comment_node 출력 ─────────────────────────────────────────────
    github_comment_id: Optional[int]
    github_comment_url: Optional[str]
