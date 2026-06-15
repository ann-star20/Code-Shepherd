"""Task 15a — edge_cases.py TDD 테스트.

두 가지 모드:
  LLM 모드  : API 키 있을 때 → _llm_detect_missing mock으로 검증
  휴리스틱 : API 키 없을 때 → 인자명 기반, 메시지에 [heuristic] 접두사

긍정 케이스 (잡아야 함) : 4개
부정 케이스 (잡으면 안 됨) : 5개  ← 긍정 못지않게 많아야 함 (PRD §5.4)
"""
import textwrap
from unittest.mock import patch

import pytest

from test_verification.edge_cases import detect


# ────────────────────────────────────────────
# Helper
# ────────────────────────────────────────────

def _write_and_detect(tmp_path, code: str):
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "f.py").write_text(textwrap.dedent(code), encoding="utf-8")
    changed = {"src/f.py": set(range(1, 100))}
    return detect(str(tmp_path), changed)


# ════════════════════════════════════════════
# 긍정 케이스 — 휴리스틱 모드 (API 키 없음, 4개)
# ════════════════════════════════════════════

def test_price_arg_heuristic_issue(tmp_path, monkeypatch):
    """price 인자 → 0/음수 엣지케이스 누락 탐지, [heuristic] 접두사."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    issues = _write_and_detect(tmp_path, """
        def calc(price):
            return price * 2
    """)
    assert len(issues) >= 1
    assert all(i.rule_id == "TEST-003" for i in issues)
    assert all(i.severity == "Minor" for i in issues)
    assert any("[heuristic]" in i.message for i in issues)


def test_rate_arg_heuristic_issue(tmp_path, monkeypatch):
    """rate 인자 → 음수/>1 엣지케이스 누락 탐지."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    issues = _write_and_detect(tmp_path, """
        def apply_discount(rate):
            return 1 - rate
    """)
    assert len(issues) >= 1
    assert all(i.rule_id == "TEST-003" for i in issues)


def test_ids_arg_heuristic_issue(tmp_path, monkeypatch):
    """ids 인자 → 빈 리스트/None 엣지케이스 누락 탐지."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    issues = _write_and_detect(tmp_path, """
        def fetch(ids):
            return [get_item(i) for i in ids]
    """)
    assert len(issues) >= 1
    assert all(i.rule_id == "TEST-003" for i in issues)


def test_llm_mode_issues_no_heuristic_prefix(tmp_path, monkeypatch):
    """OPENAI_API_KEY 있으면 LLM 모드 → _llm_detect_missing mock → [heuristic] 없음."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    with patch("test_verification.edge_cases._llm_detect_missing") as mock_llm:
        mock_llm.return_value = ["null input", "negative value"]
        issues = _write_and_detect(tmp_path, """
            def calc(price):
                return price * 2
        """)

    assert len(issues) >= 1
    assert any(i.rule_id == "TEST-003" for i in issues)
    assert not any("[heuristic]" in i.message for i in issues)


# ════════════════════════════════════════════
# 부정 케이스 — 잡으면 안 됨 (5개)
# ════════════════════════════════════════════

def test_no_args_function_zero_issues(tmp_path, monkeypatch):
    """무인자 함수 → 0 issue (spec §7.3 명시 부정 케이스)."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    issues = _write_and_detect(tmp_path, """
        def get_all():
            return []
    """)
    assert len(issues) == 0


def test_unrecognized_args_zero_issues(tmp_path, monkeypatch):
    """휴리스틱 키워드 없는 인자명 (x, y) → 0 issue."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    issues = _write_and_detect(tmp_path, """
        def add_numbers(x, y):
            return x + y
    """)
    assert len(issues) == 0


def test_empty_file_zero_issues(tmp_path, monkeypatch):
    """빈 파일 → 0 issue."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    issues = _write_and_detect(tmp_path, "")
    assert len(issues) == 0


def test_file_not_in_repo_zero_issues(tmp_path, monkeypatch):
    """changed에 있지만 파일 없음 → 0 issue (graceful)."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    changed = {"src/nonexistent.py": set(range(1, 10))}
    issues = detect(str(tmp_path), changed)
    assert len(issues) == 0


def test_llm_returns_empty_zero_issues(tmp_path, monkeypatch):
    """LLM이 빈 목록 반환 → 이슈 없음."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    with patch("test_verification.edge_cases._llm_detect_missing") as mock_llm:
        mock_llm.return_value = []
        issues = _write_and_detect(tmp_path, """
            def calc(price):
                return price * 2
        """)

    assert len(issues) == 0
