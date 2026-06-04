"""파이프라인 상태 전이 규칙 (PRD §3.9)."""

from app.domain.models import PipelineState, StagingState

# 허용된 PipelineState 전이
PIPELINE_TRANSITIONS: dict[PipelineState, set[PipelineState]] = {
    PipelineState.PENDING: {PipelineState.CRAWLING, PipelineState.FAILED},
    PipelineState.CRAWLING: {PipelineState.EXTRACTED, PipelineState.FAILED},
    PipelineState.EXTRACTED: {PipelineState.APPROVED, PipelineState.FAILED},
    PipelineState.APPROVED: {PipelineState.COMMITTED, PipelineState.FAILED},
    PipelineState.COMMITTED: set(),  # 터미널 상태
    PipelineState.FAILED: set(),  # 터미널 상태
}

# 허용된 StagingState 전이
STAGING_TRANSITIONS: dict[StagingState, set[StagingState]] = {
    StagingState.DRAFT: {StagingState.APPROVED, StagingState.REJECTED},
    StagingState.APPROVED: {StagingState.COMMITTED, StagingState.REJECTED},
    StagingState.COMMITTED: set(),  # 터미널 상태
    StagingState.REJECTED: set(),  # 터미널 상태
}


def can_transition(current: PipelineState, target: PipelineState) -> bool:
    return target in PIPELINE_TRANSITIONS.get(current, set())


def can_stage_transition(current: StagingState, target: StagingState) -> bool:
    return target in STAGING_TRANSITIONS.get(current, set())
