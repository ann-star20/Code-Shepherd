"""
공통 LangGraph State 스키마 — 모든 모듈이 공유하는 단일 진실의 원천.

사용법:
    from common.state import PlatformState, AgentStatus, RequestType

모든 모듈은 PlatformState를 기반으로 동작한다.
모듈 전용 필드가 필요하면 PlatformState를 상속하되,
공통 필드는 절대 재정의하지 않는다.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class RequestType(str, Enum):
    PR_REVIEW    = "pr_review"
    KMS_QUERY    = "kms_query"
    ONBOARDING   = "onboarding"
    ARCHITECTURE = "architecture"


class AgentStatus(str, Enum):
    RUNNING      = "running"
    SUCCESS      = "success"
    FAIL         = "fail"
    HITL_PENDING = "hitl_pending"
    ESCALATED    = "escalated"


class SkillLevel(str, Enum):
    JUNIOR = "junior"
    MID    = "mid"
    SENIOR = "senior"


class Severity(str, Enum):
    CRITICAL = "Critical"
    MAJOR    = "Major"
    MINOR    = "Minor"


class ValidationResult(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"


# ---------------------------------------------------------------------------
# 서브 모델 (Pydantic BaseModel)
# ---------------------------------------------------------------------------

class DeveloperInfo(BaseModel):
    model_config = ConfigDict(strict=True)

    user_id:     str
    github_id:   str
    skill_level: SkillLevel
    tech_stack:  list[str] = Field(default_factory=list)


class PRContext(BaseModel):
    model_config = ConfigDict(strict=True)

    pr_id:            str
    pr_diff:          str
    repo:             str
    author_github_id: str


class KMSContext(BaseModel):
    model_config = ConfigDict(strict=True)

    architecture_docs:  list[str] = Field(default_factory=list)
    coding_conventions: str       = ""
    previous_pr_issues: list[str] = Field(default_factory=list)


class IssueItem(BaseModel):
    model_config = ConfigDict(strict=True)

    severity:   Severity
    line:       int
    file:       str
    message:    str
    rule_id:    str
    suggestion: str


class IssueSummary(BaseModel):
    model_config = ConfigDict(strict=True)

    critical: int = 0
    major:    int = 0
    minor:    int = 0


class AgentResult(BaseModel):
    """Output Contract — 모든 Agent의 출력이 이 형식을 따른다."""

    model_config = ConfigDict(strict=True)

    task_id:           str
    trace_id:          str
    agent_name:        str
    module_id:         str
    status:            AgentStatus
    issues:            list[IssueItem]  = Field(default_factory=list)
    summary:           IssueSummary     = Field(default_factory=IssueSummary)
    validation_result: ValidationResult = ValidationResult.SKIP
    execution_ms:      int
    next_agent:        Optional[str]    = None


# ---------------------------------------------------------------------------
# 공통 LangGraph State (TypedDict — LangGraph 호환)
# ---------------------------------------------------------------------------

from typing import TypedDict


class PlatformState(TypedDict, total=False):
    """
    모든 모듈이 공유하는 LangGraph State.

    total=False: 모든 필드가 optional.
    각 모듈은 자신이 담당하는 필드만 채운다.

    필드 책임:
        task_id, trace_id, request_type, developer, pr_context, kms_context
            → Module 1 (Orchestrator) 초기화
        analysis_results, issues
            → Module 2/3 (병렬 분석) 추가
        validation_result, retry_count, status, next_agent, error_message
            → 각 모듈이 자신의 처리 결과를 기록
    """

    # Module 1이 초기화
    task_id:      str
    trace_id:     str
    request_type: RequestType
    module_id:    str

    # Module 1이 채움 (요청 파싱)
    developer:   DeveloperInfo
    pr_context:  PRContext          # PR 리뷰 시에만
    kms_context: KMSContext         # KMS 검색 후

    # Module 2/3이 채움 (병렬 분석 결과 누적)
    analysis_results: list[AgentResult]
    issues:           list[IssueItem]

    # 각 모듈이 채움
    validation_result: str          # "pass | fail | skip"
    retry_count:       int
    status:            AgentStatus
    next_agent:        str          # None이면 END
    error_message:     str          # 실패 시


# ---------------------------------------------------------------------------
# 모듈별 State 확장 (공통 필드 재정의 금지)
# ---------------------------------------------------------------------------

class Module2State(PlatformState, total=False):
    """Module 2 전용 추가 필드."""
    static_analysis_raw: str        # ESLint/Pylint 원본 출력
    security_scan_raw:   str        # 보안 스캔 원본 출력


class Module3State(PlatformState, total=False):
    """Module 3 전용 추가 필드."""
    coverage_raw:        str        # 커버리지 측정 원본 출력
    performance_raw:     str        # 성능 분석 원본 출력


class Module4State(PlatformState, total=False):
    """Module 4 전용 추가 필드."""
    verdict:            str         # "lgtm | rework | escalate"
    comment_body:       str         # GitHub 코멘트 마크다운
    learning_resources: list[dict]  # 학습 자료 목록
    onboarding_update:  dict        # 온보딩 이력 갱신 데이터
    escalation:         dict        # Slack 에스컬레이션 정보


# ---------------------------------------------------------------------------
# Module 5 전용 독립 State (PlatformState와 완전 분리)
# ---------------------------------------------------------------------------

class Module5State(TypedDict, total=False):
    """
    Module 5 (GraphDB + YouTube) 전용 State.
    PlatformState를 사용하지 않는 독립 파이프라인.

    doc_id / file_hash를 공통 키로 보존하여 향후 KMS 연결 가능.
    """

    # 공통 키 (향후 KMS 연결을 위해 필수 보존)
    doc_id:            str          # UUID v4 — 반드시 생성
    file_hash:         str          # SHA-256 — 중복 감지 + KMS 매칭용
    source_system:     str          # 항상 "graph_youtube"
    original_filename: str

    # 처리 결과
    entities:          list[dict]   # 추출된 엔티티 목록
    relations:         list[dict]   # 엔티티 간 관계 목록
    keywords:          list[str]    # 핵심 키워드 목록
    recommend_query:   list[str]    # YouTube 검색 쿼리 목록
    youtube_results:   list[dict]   # YouTube 추천 결과

    # 상태
    status:            str          # "stored | failed"
    error_message:     str          # 실패 시
