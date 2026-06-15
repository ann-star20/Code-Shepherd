"""R3 — config/conventions.py TDD 테스트 (RAG 설계서 §5ⓐ, 위험 3).

정량 기준(커버리지%)은 RAG 자연어 파싱이 아니라 구조화 dict로 관리한다.
threshold_for(file_path) → 파일 경로의 모듈을 보고 사내 기준값 반환.
"""
import pytest


def test_payment_module_threshold_90():
    """결제 모듈 → 0.90."""
    from config.conventions import threshold_for
    assert threshold_for("src/payment/billing.py") == 0.90


def test_auth_module_threshold_90():
    """인증 모듈 → 0.90."""
    from config.conventions import threshold_for
    assert threshold_for("src/auth/login.py") == 0.90


def test_legacy_module_threshold_70():
    """레거시 모듈 → 0.70 (dict에 있는 값, 죽은 설정 아님)."""
    from config.conventions import threshold_for
    assert threshold_for("src/legacy/old_api.py") == 0.70


def test_default_threshold_80():
    """일반 파일 → 기본 0.80."""
    from config.conventions import threshold_for
    assert threshold_for("src/cart.py") == 0.80


def test_windows_path_separator():
    """역슬래시 경로도 모듈 판별 동작 (coverage가 Windows 경로 줄 수 있음)."""
    from config.conventions import threshold_for
    assert threshold_for("src\\payment\\billing.py") == 0.90


def test_rules_dict_has_default():
    """COVERAGE_RULES에 default 키 존재 (fallback 보장)."""
    from config.conventions import COVERAGE_RULES
    assert "default" in COVERAGE_RULES
    assert COVERAGE_RULES["default"] == 0.80
