"""llm_judge 테스트 — mock no-op / Minor 스킵 / 재판단 / graceful fallback.

실제 LLM API 없이 통과해야 한다(_call_llm_with_retry를 Mock).
USE_MOCK_LLM=false로 강제해 실제 경로 로직을 검증하되 LLM 호출은 stub 처리한다.
"""

import asyncio

import pytest

from app.services import llm_judge
from shared.contracts import AnalysisContext, DeveloperProfile, IssueItem


def _issue(severity: str, rule_id: str = "SA-X") -> IssueItem:
    return IssueItem(
        severity=severity, line=1, file="a.py", message="m", rule_id=rule_id, suggestion="orig"
    )


def _ctx() -> AnalysisContext:
    return AnalysisContext(
        coding_conventions="snake_case 사용",
        previous_pr_issues=["N+1 쿼리"],
        architecture_docs=["서비스 레이어 분리"],
    )


# ── mock no-op ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mock_is_noop(monkeypatch):
    monkeypatch.setenv("USE_MOCK_LLM", "true")
    issues = [_issue("Critical")]
    out = await llm_judge.judge_issues(issues, _ctx(), None)
    assert out is issues  # 원본 그대로(무해 no-op)
    assert out[0].suggestion == "orig"


# ── Minor 스킵 ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_minor_skipped(monkeypatch):
    monkeypatch.setenv("USE_MOCK_LLM", "false")
    called = {"n": 0}

    async def _spy(prompt, model_id, max_retries=1):
        called["n"] += 1
        return {"severity": "Critical", "suggestion": "x"}

    monkeypatch.setattr(llm_judge, "_call_llm_with_retry", _spy)
    out = await llm_judge.judge_issues([_issue("Minor")], _ctx(), None)
    assert called["n"] == 0  # Minor는 LLM 호출 안 함
    assert out[0].severity == "Minor"


# ── 재판단 (severity/suggestion 갱신) ──────────────────────────────────────

@pytest.mark.asyncio
async def test_rejudge_updates_severity(monkeypatch):
    monkeypatch.setenv("USE_MOCK_LLM", "false")

    async def _fake(prompt, model_id, max_retries=1):
        return {"severity": "Critical", "suggestion": "parameterize query", "rationale": "r"}

    monkeypatch.setattr(llm_judge, "_call_llm_with_retry", _fake)
    out = await llm_judge.judge_issues([_issue("Major")], _ctx(), DeveloperProfile(id="d1"))
    assert out[0].severity == "Critical"
    assert out[0].suggestion == "parameterize query"


# ── 파싱 실패({}) → 원본 유지 ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_empty_result_keeps_original(monkeypatch):
    monkeypatch.setenv("USE_MOCK_LLM", "false")

    async def _empty(prompt, model_id, max_retries=1):
        return {}

    monkeypatch.setattr(llm_judge, "_call_llm_with_retry", _empty)
    out = await llm_judge.judge_issues([_issue("Major")], _ctx(), None)
    assert out[0].severity == "Major"
    assert out[0].suggestion == "orig"


# ── 개별 이슈 예외 → 원본 fallback (전체 중단 없음) ────────────────────────

@pytest.mark.asyncio
async def test_exception_falls_back_to_original(monkeypatch):
    monkeypatch.setenv("USE_MOCK_LLM", "false")

    async def _boom(prompt, model_id, max_retries=1):
        raise RuntimeError("api down")

    monkeypatch.setattr(llm_judge, "_call_llm_with_retry", _boom)
    out = await llm_judge.judge_issues([_issue("Critical")], _ctx(), None)
    assert out[0].severity == "Critical"
    assert out[0].suggestion == "orig"


# ── 타임아웃 → 원본 유지 ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_timeout_keeps_original(monkeypatch):
    monkeypatch.setenv("USE_MOCK_LLM", "false")
    monkeypatch.setattr(llm_judge, "LLM_TIMEOUT_SEC", 0.01)

    async def _slow(prompt, model_id, max_retries=1):
        await asyncio.sleep(1)
        return {"severity": "Minor", "suggestion": "x"}

    monkeypatch.setattr(llm_judge, "_call_llm_with_retry", _slow)
    out = await llm_judge.judge_issues([_issue("Major")], _ctx(), None)
    assert out[0].severity == "Major"


# ── summary 재계산 ─────────────────────────────────────────────────────────

def test_summarize_recounts():
    s = llm_judge.summarize([_issue("Critical"), _issue("Major"), _issue("Minor")])
    assert (s.critical, s.major, s.minor) == (1, 1, 1)


# ── 프롬프트에 context 3필드 주입 ──────────────────────────────────────────

def test_prompt_injects_context():
    p = llm_judge.build_judge_prompt(_issue("Major"), _ctx(), "junior", ["python"])
    assert "snake_case 사용" in p
    assert "N+1 쿼리" in p
    assert "서비스 레이어 분리" in p
