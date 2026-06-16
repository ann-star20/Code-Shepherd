"""Task 15b — memory_leak.py TDD 테스트.

AST 후보 탐지 + LLM 교차검증:
  AST: open() 단독 호출, 전역 list 무한 append
  LLM: 후보 교차검증 → confidence < 0.7 제외
  키 없으면: AST 후보 그대로 → [heuristic] 접두사

긍정 케이스 (잡아야 함) : 4개
부정 케이스 (잡으면 안 됨) : 5개  ← 긍정 못지않게 많아야 함 (PRD §5.4)
"""
import textwrap
from unittest.mock import patch

import pytest

from performance.memory_leak import detect, LeakVerification


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
# 긍정 케이스 (4개)
# ════════════════════════════════════════════

def test_standalone_open_heuristic_issue(tmp_path, monkeypatch):
    """open() 단독 호출(with/대입 없음) → PERF-003, [heuristic] 접두사."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    issues = _write_and_detect(tmp_path, """
        open("data.txt")
    """)
    assert len(issues) == 1
    assert issues[0].rule_id == "PERF-003"
    assert issues[0].severity == "Minor"
    assert "[heuristic]" in issues[0].message


def test_global_list_append_heuristic_issue(tmp_path, monkeypatch):
    """전역 list에 함수 내부에서 append → PERF-003, [heuristic] 접두사."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    issues = _write_and_detect(tmp_path, """
        CACHE = []

        def add_item(x):
            CACHE.append(x)
    """)
    assert len(issues) >= 1
    assert any(i.rule_id == "PERF-003" for i in issues)
    assert any("[heuristic]" in i.message for i in issues)


def test_llm_confirms_leak_issue(tmp_path, monkeypatch):
    """LLM이 누수 확인 (confidence >= 0.7) → PERF-003, [heuristic] 없음."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    with patch("performance.memory_leak._llm_verify_leak") as mock_llm:
        mock_llm.return_value = LeakVerification(
            is_leak=True, confidence=0.9, reason="unclosed file handle"
        )
        issues = _write_and_detect(tmp_path, """
            open("data.txt")
        """)

    assert len(issues) >= 1
    assert issues[0].rule_id == "PERF-003"
    assert "[heuristic]" not in issues[0].message


def test_multiple_standalone_opens_multiple_issues(tmp_path, monkeypatch):
    """open() 단독 호출 2회 → 2개 이슈 (각각 다른 줄)."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    issues = _write_and_detect(tmp_path, """
        open("a.txt")
        open("b.txt")
    """)
    assert len(issues) == 2
    assert all(i.rule_id == "PERF-003" for i in issues)


# ════════════════════════════════════════════
# 부정 케이스 — 잡으면 안 됨 (5개)
# ════════════════════════════════════════════

def test_with_open_zero_issues(tmp_path, monkeypatch):
    """with open() → 0 issue (파일이 자동으로 닫힘)."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    issues = _write_and_detect(tmp_path, """
        with open("data.txt") as f:
            content = f.read()
    """)
    assert len(issues) == 0


def test_assigned_open_zero_issues(tmp_path, monkeypatch):
    """fh = open(...) → 0 issue (대입됨, 닫기 가능)."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    issues = _write_and_detect(tmp_path, """
        fh = open("data.txt")
        content = fh.read()
        fh.close()
    """)
    assert len(issues) == 0


def test_local_list_append_zero_issues(tmp_path, monkeypatch):
    """로컬 list append (함수 내부 지역 변수) → 0 issue."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    issues = _write_and_detect(tmp_path, """
        def process(items):
            result = []
            for item in items:
                result.append(item)
            return result
    """)
    assert len(issues) == 0


def test_llm_low_confidence_zero_issues(tmp_path, monkeypatch):
    """LLM confidence < 0.7 → 오탐 제거 → 0 issue."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    with patch("performance.memory_leak._llm_verify_leak") as mock_llm:
        mock_llm.return_value = LeakVerification(
            is_leak=True, confidence=0.5, reason="might be ok"
        )
        issues = _write_and_detect(tmp_path, """
            open("data.txt")
        """)

    assert len(issues) == 0


def test_llm_says_no_leak_zero_issues(tmp_path, monkeypatch):
    """LLM is_leak=False → 0 issue."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    with patch("performance.memory_leak._llm_verify_leak") as mock_llm:
        mock_llm.return_value = LeakVerification(
            is_leak=False, confidence=0.85, reason="short-lived object"
        )
        issues = _write_and_detect(tmp_path, """
            open("data.txt")
        """)

    assert len(issues) == 0
