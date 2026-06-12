"""B2: config/settings.py — 상수 및 환경변수 설정 검증."""
from config.settings import (
    CRITICAL_ESCALATE_THRESHOLD,
    MAJOR_REWORK_THRESHOLD,
    SKILL_LEVELS,
    LLM_MODEL,
)


class TestThresholds:
    def test_critical_escalate_threshold_is_1(self):
        assert CRITICAL_ESCALATE_THRESHOLD == 1

    def test_major_rework_threshold_is_3(self):
        assert MAJOR_REWORK_THRESHOLD == 3


class TestSkillLevels:
    def test_junior_in_skill_levels(self):
        assert "junior" in SKILL_LEVELS

    def test_mid_in_skill_levels(self):
        assert "mid" in SKILL_LEVELS

    def test_senior_in_skill_levels(self):
        assert "senior" in SKILL_LEVELS

    def test_skill_levels_is_set(self):
        assert isinstance(SKILL_LEVELS, (set, frozenset))


class TestLLMModel:
    def test_llm_model_is_string(self):
        assert isinstance(LLM_MODEL, str)

    def test_llm_model_not_empty(self):
        assert len(LLM_MODEL) > 0
