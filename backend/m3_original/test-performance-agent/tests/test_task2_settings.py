"""Task 2 — config/settings.py: 상수 일원화 테스트."""


def test_coverage_threshold_default():
    from config.settings import COVERAGE_THRESHOLD
    assert COVERAGE_THRESHOLD == 0.80


def test_db_call_names_narrow_set():
    """§18 원칙: DB_CALL_NAMES는 좁게 시작 — 핵심 DB 호출만 포함."""
    from config.settings import DB_CALL_NAMES
    required = {"query", "execute", "filter", "fetchone", "fetchall", "scalar"}
    assert required.issubset(DB_CALL_NAMES)


def test_db_call_names_excludes_generic_methods():
    """PRD §5.4 nplus1 부정 케이스: .get/.all/.first/.count는 제외해야 함."""
    from config.settings import DB_CALL_NAMES
    excluded = {"get", "all", "first", "count"}
    assert excluded.isdisjoint(DB_CALL_NAMES), (
        f"오탐 유발 메서드가 DB_CALL_NAMES에 포함됨: {excluded & DB_CALL_NAMES}"
    )


def test_complexity_depths():
    from config.settings import COMPLEXITY_MINOR_DEPTH, COMPLEXITY_MAJOR_DEPTH
    assert COMPLEXITY_MINOR_DEPTH == 2
    assert COMPLEXITY_MAJOR_DEPTH == 3


def test_timeouts_defined():
    from config.settings import (
        AGENT_TIMEOUT_S, DOCKER_TIMEOUT_S, COV_TIMEOUT_S, LLM_TIMEOUT_S
    )
    assert AGENT_TIMEOUT_S == 30
    assert DOCKER_TIMEOUT_S == 120
    assert COV_TIMEOUT_S == 15
    assert LLM_TIMEOUT_S == 8


def test_llm_settings():
    from config.settings import LLM_CONFIDENCE_MIN, FALSE_ALARM_THRESHOLD
    assert LLM_CONFIDENCE_MIN == 0.7
    assert FALSE_ALARM_THRESHOLD == 0.10
