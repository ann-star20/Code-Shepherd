"""파이프라인 품질 모니터링 지표 계산. PRD §24."""

from __future__ import annotations

from dataclasses import dataclass

HITL_RETRIGGER_THRESHOLD = 0.20
SCHEMA_DEVIATION_ALERT_THRESHOLD = 1


@dataclass
class HitlMetrics:
    rate: float
    should_retrigger: bool


@dataclass
class SchemaDeviationMetrics:
    count: int
    should_alert: bool


def check_hitl_correction_rate(total_count: int, corrected_count: int) -> HitlMetrics:
    """HITL 수정률 ≥ 20% 시 프롬프트 재평가 트리거 여부 반환."""
    if total_count == 0:
        return HitlMetrics(rate=0.0, should_retrigger=False)
    rate = corrected_count / total_count
    return HitlMetrics(rate=rate, should_retrigger=rate >= HITL_RETRIGGER_THRESHOLD)


def check_schema_deviation(deviation_count: int) -> SchemaDeviationMetrics:
    """스키마 이탈 1건 이상 시 Slack 알림 여부 반환."""
    return SchemaDeviationMetrics(
        count=deviation_count,
        should_alert=deviation_count >= SCHEMA_DEVIATION_ALERT_THRESHOLD,
    )
