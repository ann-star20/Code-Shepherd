from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from module_0_kms.pipeline._gemini import _get_gemini_llm, call_gemini_with_retry


# ---------------------------------------------------------------------------
# T4-A: LLM 싱글턴 검증
# ---------------------------------------------------------------------------

def test_get_gemini_llm_returns_singleton(monkeypatch):
    """
    _get_gemini_llm()은 두 번 호출해도 ChatGoogleGenerativeAI를 한 번만 생성해야 한다.
    """
    import module_0_kms.pipeline._gemini as m
    m._gemini_llm = None  # 싱글턴 리셋

    fake_llm = MagicMock()
    with patch("kms.pipeline._gemini.ChatGoogleGenerativeAI", return_value=fake_llm) as MockLLM:
        llm1 = _get_gemini_llm()
        llm2 = _get_gemini_llm()

    assert llm1 is llm2, "두 번 호출 시 같은 객체를 반환해야 한다"
    assert MockLLM.call_count == 1, (
        f"ChatGoogleGenerativeAI 생성자가 {MockLLM.call_count}회 호출됨 — 1회만 허용"
    )


# ---------------------------------------------------------------------------
# T4-B: tenacity 재시도 검증
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_call_gemini_with_retry_succeeds_after_failures(monkeypatch):
    """
    일시적 오류 후 성공 시 최대 2회 재시도하고 결과를 반환해야 한다.
    """
    import module_0_kms.pipeline._gemini as m

    call_count = 0

    async def flaky_ainvoke(_messages):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise RuntimeError("transient Gemini error")
        return MagicMock(content='{"score": 0.9}')

    fake_llm = MagicMock()
    fake_llm.ainvoke = flaky_ainvoke
    m._gemini_llm = fake_llm

    # tenacity의 asyncio.sleep을 즉시 반환으로 대체 (테스트 속도)
    monkeypatch.setattr("asyncio.sleep", AsyncMock())

    result = await call_gemini_with_retry([MagicMock()])

    assert call_count == 3, (
        f"2회 실패 후 3번째 성공이어야 하지만 {call_count}회 호출됨"
    )
    assert result.content == '{"score": 0.9}'


@pytest.mark.asyncio
async def test_call_gemini_with_retry_raises_after_max_retries(monkeypatch):
    """
    모든 재시도가 실패하면 예외를 전파해야 한다 (reraise=True).
    """
    import module_0_kms.pipeline._gemini as m

    async def always_fail(_messages):
        raise RuntimeError("persistent Gemini error")

    fake_llm = MagicMock()
    fake_llm.ainvoke = always_fail
    m._gemini_llm = fake_llm

    monkeypatch.setattr("asyncio.sleep", AsyncMock())

    with pytest.raises(RuntimeError, match="persistent Gemini error"):
        await call_gemini_with_retry([MagicMock()])
