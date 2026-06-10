"""서비스 간 요청/응답 Pydantic DTO (계약의 단일 출처 — SSoT).

오케스트레이터(m1)가 각 모듈을 호출할 때 사용하는 입출력 계약.
모듈 팀은 이 파일의 DTO에 맞춰 엔드포인트를 구현한다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 공통
# ---------------------------------------------------------------------------

class IssueItem(BaseModel):
    severity: Literal["Critical", "Major", "Minor"]
    line: int | None = None
    file: str | None = None
    message: str
    rule_id: str | None = None
    suggestion: str | None = None


class IssueSummary(BaseModel):
    critical: int = 0
    major: int = 0
    minor: int = 0


# ---------------------------------------------------------------------------
# m0 — KMS 인제스트
# ---------------------------------------------------------------------------

class M0IngestRequest(BaseModel):
    task_id: str = Field(..., description="UUID — 트리거 단위 추적 키")
    source: Literal["upload", "notion", "confluence", "slack"] = "upload"
    doc_id: str = Field(..., description="처리할 문서 ID")
    trace_id: str | None = None


class M0IngestResponse(BaseModel):
    task_id: str
    status: Literal["accepted", "processing", "done", "failed"] = "accepted"
    message: str = "Stub — not implemented"


# ---------------------------------------------------------------------------
# m2 — 정적 분석·보안 스캔
# ---------------------------------------------------------------------------

class AnalysisContext(BaseModel):
    architecture_docs: list[str] = Field(default_factory=list)
    coding_conventions: str = ""
    previous_pr_issues: list[str] = Field(default_factory=list)


class DeveloperProfile(BaseModel):
    id: str
    skill_level: Literal["junior", "mid", "senior"] = "junior"
    tech_stack: list[str] = Field(default_factory=list)


class M2AnalyzeRequest(BaseModel):
    task_id: str
    pr_id: str
    pr_diff: str
    context: AnalysisContext = Field(default_factory=AnalysisContext)
    developer: DeveloperProfile | None = None
    trace_id: str | None = None


class M2AnalyzeResponse(BaseModel):
    task_id: str
    agent: Literal["static_analysis", "security_scan"]
    issues: list[IssueItem] = Field(default_factory=list)
    summary: IssueSummary = Field(default_factory=IssueSummary)
    execution_ms: int = 0


# ---------------------------------------------------------------------------
# m3 — 테스트 검증·성능 분석
# ---------------------------------------------------------------------------

class M3VerifyRequest(BaseModel):
    task_id: str
    pr_id: str
    pr_diff: str
    # 선택: 실제 분석(clone→run)에 필요. 없으면 빈 issues 반환(가짜 만들지 않음).
    # 하위호환 — m1이 아직 안 보내도 됨(None).
    clone_url: str | None = None
    commit_sha: str | None = None
    context: AnalysisContext = Field(default_factory=AnalysisContext)
    developer: DeveloperProfile | None = None
    trace_id: str | None = None


class M3VerifyResponse(BaseModel):
    task_id: str
    agent: Literal["test_verification", "performance"]
    issues: list[IssueItem] = Field(default_factory=list)
    summary: IssueSummary = Field(default_factory=IssueSummary)
    # 측정 지표(선택, additive) — test_verification 은 커버리지 등을 담는다.
    # 코멘트 '📊 지표 줄'용. 미설정(None)이면 소비자는 그냥 무시 → 하위호환.
    metrics: dict | None = None
    execution_ms: int = 0


class M3ReviewRequest(BaseModel):
    """4개 모듈 결과를 모아 판정·코멘트·게시를 요청 (M4EvaluateRequest 동형 + repository/pr_number)."""
    task_id: str
    pr_id: str
    repository: str  # "owner/repo" — 코멘트를 게시할 대상
    pr_number: int
    static_analysis: M2AnalyzeResponse | None = None
    security_scan: M2AnalyzeResponse | None = None
    test_verification: M3VerifyResponse | None = None
    performance: M3VerifyResponse | None = None
    developer: DeveloperProfile | None = None
    trace_id: str | None = None


class M3ReviewResponse(BaseModel):
    task_id: str
    pr_id: str
    verdict: Literal["lgtm", "rework", "escalate"] = "lgtm"
    comment_posted: bool = False
    comment_url: str | None = None
    persisted: bool = False


# ---------------------------------------------------------------------------
# m4 — 커리큘럼·판정
# ---------------------------------------------------------------------------

class M4EvaluateRequest(BaseModel):
    task_id: str
    pr_id: str
    static_analysis: M2AnalyzeResponse | None = None
    security_scan: M2AnalyzeResponse | None = None
    test_verification: M3VerifyResponse | None = None
    performance: M3VerifyResponse | None = None
    developer: DeveloperProfile | None = None
    trace_id: str | None = None


class M4EvaluateResponse(BaseModel):
    task_id: str
    pr_id: str
    verdict: Literal["lgtm", "rework", "escalate"] = "lgtm"
    comment_body: str = "Stub — not implemented"
    execution_ms: int = 0


class M4CurriculumRequest(BaseModel):
    task_id: str
    developer: DeveloperProfile
    trace_id: str | None = None


class M4CurriculumResponse(BaseModel):
    task_id: str
    developer_id: str
    roadmap: list[str] = Field(default_factory=list)
    message: str = "Stub — not implemented"


# ---------------------------------------------------------------------------
# m5 — GraphDB + YouTube (독립 모듈)
# ---------------------------------------------------------------------------

class M5ExtractRequest(BaseModel):
    task_id: str = Field(..., description="UUID — 트리거 단위 추적 키")
    doc_id: str = Field(..., description="그래프 노드 연결 키 (필수)")
    source: Literal["upload", "manual"] = "upload"
    trace_id: str | None = None


class M5ExtractResponse(BaseModel):
    task_id: str
    doc_id: str
    status: Literal["accepted", "processing", "done", "failed"] = "accepted"
    entity_count: int = 0
    relationship_count: int = 0
    message: str = "Stub — not implemented"


class YoutubeVideoItem(BaseModel):
    title: str
    url: str
    video_id: str | None = None


class M5YoutubeRecommendRequest(BaseModel):
    task_id: str
    keywords: list[str] = Field(default_factory=list)
    doc_id: str | None = None
    trace_id: str | None = None


class M5YoutubeRecommendResponse(BaseModel):
    task_id: str
    videos: list[YoutubeVideoItem] = Field(default_factory=list)
    message: str = "Stub — not implemented"


# ---------------------------------------------------------------------------
# 트리거 공통
# ---------------------------------------------------------------------------

class PRTriggerPayload(BaseModel):
    """GitHub Webhook payload (간소화 — m1 라우팅에 필요한 필드만)."""
    action: str
    pr_id: str | None = None
    pr_diff: str = ""
    sender_login: str | None = None
    repository: str | None = None
    trace_id: str | None = None


class DocumentTriggerPayload(BaseModel):
    """문서 업로드 완료 신호."""
    doc_id: str
    source: Literal["upload", "notion", "confluence", "slack"] = "upload"
    trace_id: str | None = None
