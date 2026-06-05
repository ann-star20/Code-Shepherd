"""Phase 4 G17 — 모니터링 지표 계산 테스트.

T_mon_01: corrected/total ≥ 20% → should_retrigger=True
T_mon_02: corrected/total < 20% → should_retrigger=False
T_mon_03: total=0 → rate=0.0, should_retrigger=False
T_mon_04: deviation_count ≥ 1 → should_alert=True
T_mon_05: deviation_count = 0 → should_alert=False
"""
from app.infrastructure.langsmith.monitor import (
    check_hitl_correction_rate,
    check_schema_deviation,
)


def test_T_mon_01_hitl_rate_above_threshold_triggers():
    """Arrange: total=10, corrected=3 (30%).
    Act: check_hitl_correction_rate.
    Assert: rate≈0.30, should_retrigger=True.
    """
    m = check_hitl_correction_rate(total_count=10, corrected_count=3)
    assert abs(m.rate - 0.30) < 1e-9
    assert m.should_retrigger is True


def test_T_mon_02_hitl_rate_below_threshold_no_trigger():
    """Arrange: total=10, corrected=1 (10%).
    Act: check_hitl_correction_rate.
    Assert: rate=0.10, should_retrigger=False.
    """
    m = check_hitl_correction_rate(total_count=10, corrected_count=1)
    assert abs(m.rate - 0.10) < 1e-9
    assert m.should_retrigger is False


def test_T_mon_03_hitl_rate_exact_threshold_triggers():
    """Arrange: total=5, corrected=1 (20% 정확히).
    Act: check_hitl_correction_rate.
    Assert: should_retrigger=True (경계값 포함).
    """
    m = check_hitl_correction_rate(total_count=5, corrected_count=1)
    assert abs(m.rate - 0.20) < 1e-9
    assert m.should_retrigger is True


def test_T_mon_04_hitl_total_zero_noop():
    """Arrange: total=0 (빈 세션).
    Act: check_hitl_correction_rate.
    Assert: rate=0.0, should_retrigger=False (ZeroDivision 없음).
    """
    m = check_hitl_correction_rate(total_count=0, corrected_count=0)
    assert m.rate == 0.0
    assert m.should_retrigger is False


def test_T_mon_05_schema_deviation_above_threshold_alerts():
    """Arrange: deviation_count=2.
    Act: check_schema_deviation.
    Assert: should_alert=True.
    """
    m = check_schema_deviation(deviation_count=2)
    assert m.count == 2
    assert m.should_alert is True


def test_T_mon_06_schema_deviation_zero_no_alert():
    """Arrange: deviation_count=0.
    Act: check_schema_deviation.
    Assert: should_alert=False.
    """
    m = check_schema_deviation(deviation_count=0)
    assert m.count == 0
    assert m.should_alert is False
