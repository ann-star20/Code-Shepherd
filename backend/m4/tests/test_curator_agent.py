"""T11 단위 테스트 — Curator 에이전트 (개발자 프로필 + 이슈 → curator_instruction, D22) (Mock 기반, 실 LLM 없이).

User journey:
  As the Phase 2 learning pipeline, I want to ask the Curator agent for a
  curator_instruction built from a developer's profile and the current review
  issue, so that depth/card_type/RAG 검색 필드를 이 개발자에게 맞게 동적으로 정할 수 있다
  (D22 — Phase 1의 고정 규칙 D16/D18/D15를 대체).
"""

import json
import uuid
from types import SimpleNamespace

import pytest

from app.models.review_issue import ReviewIssue
from app.pipeline import curator_agent as curator_agent_module
from app.pipeline.curator_agent import DeveloperProfile, curator_agent


def make_issue(**overrides) -> ReviewIssue:
    defaults = dict(
        id=uuid.uuid4(),
        severity="critical",
        keyword="SQL Injection",
        sub_category="input validation",
        code_context="상품 검색 기능 — 사용자 입력을 쿼리에 직접 삽입",
        code_snippet=(
            "def search_products(keyword):\n"
            "    query = f\"SELECT * FROM products WHERE name LIKE '%{keyword}%'\"\n"
            "    return db.execute(query)"
        ),
        suggestion="파라미터 바인딩을 사용해 쿼리를 작성한다",
        programming_language="Python",
        framework="FastAPI",
        framework_version="0.104.0",
        name_of_function="search_products",
    )
    defaults.update(overrides)
    return ReviewIssue(**defaults)


def make_profile(**overrides) -> DeveloperProfile:
    defaults: DeveloperProfile = {
        "weak_categories": ["input validation", "authentication"],
        "past_mistakes": ["SQL Injection (review_issue#1)", "SQL Injection (review_issue#2)"],
    }
    defaults.update(overrides)
    return defaults


FIXED_INSTRUCTION = {
    "depth": "deep",
    "focus": "파라미터 바인딩 vs 문자열 포매팅의 차이",
    "analogy": "자물쇠에 맞는 열쇠를 매번 새로 깎지 않고 마스터키 틀에 끼워 쓰는 것",
    "key_points": ["사용자 입력은 절대 쿼리 문자열에 직접 삽입하지 않는다", "파라미터 바인딩을 사용한다"],
    "card_type": "code_fix",
    "query_fields": {"category": "security_guide", "topic": "SQL Injection prevention"},
}


def _capture_curator_prompt(monkeypatch) -> list[str]:
    """genai.GenerativeModel을 대체해 curator_agent가 실제로 구성한 프롬프트 문자열을 캡처한다."""
    captured: list[str] = []

    class FakeGenerativeModel:
        def __init__(self, *_args, **_kwargs):
            pass

        async def generate_content_async(self, prompt, **_kwargs):
            captured.append(prompt)
            return SimpleNamespace(text=json.dumps(FIXED_INSTRUCTION))

    monkeypatch.setattr(curator_agent_module.genai, "GenerativeModel", FakeGenerativeModel)
    return captured


@pytest.mark.asyncio
async def test_curator_agent_returns_curator_instruction_with_expected_keys(monkeypatch):
    """LLM이 반환한 JSON을 D22 계약의 6개 키(depth/focus/analogy/key_points/card_type/query_fields)를 가진 dict로 그대로 반환한다."""
    _capture_curator_prompt(monkeypatch)

    instruction = await curator_agent(profile=make_profile(), issue=make_issue())

    assert instruction == FIXED_INSTRUCTION
    assert set(instruction.keys()) == {"depth", "focus", "analogy", "key_points", "card_type", "query_fields"}


@pytest.mark.asyncio
async def test_curator_agent_prompt_includes_profile_and_issue_details(monkeypatch):
    """프롬프트에 개발자의 약점 분야(weak_categories)/과거 실수 이력(past_mistakes)과 이번 이슈의 keyword/severity가 포함된다."""
    captured = _capture_curator_prompt(monkeypatch)
    profile = make_profile(weak_categories=["input validation"], past_mistakes=["SQL Injection 반복 발생"])
    issue = make_issue(keyword="SQL Injection", severity="critical")

    await curator_agent(profile=profile, issue=issue)

    prompt = captured[0]
    assert "input validation" in prompt
    assert "SQL Injection 반복 발생" in prompt
    assert "SQL Injection" in prompt
    assert "critical" in prompt


@pytest.mark.asyncio
async def test_curator_agent_prompt_omits_retry_hint_when_first_attempt(monkeypatch):
    """최초 호출(hint=None)에는 재시도 안내 문구가 프롬프트에 들어가지 않는다 — 불필요한 지시로 결과를 흔들지 않기 위함."""
    captured = _capture_curator_prompt(monkeypatch)

    await curator_agent(profile=make_profile(), issue=make_issue())

    prompt = captured[0]
    assert "검색 범위를 좁혀" not in prompt
    assert "다른 설명 방식" not in prompt


@pytest.mark.asyncio
async def test_curator_agent_prompt_narrows_query_on_low_faithfulness_hint(monkeypatch):
    """hint='narrow_query'(D26 — low_faithfulness 재시도)면 query_fields 검색 범위를 좁히라는 지시가 추가된다."""
    captured = _capture_curator_prompt(monkeypatch)

    await curator_agent(profile=make_profile(), issue=make_issue(), hint="narrow_query")

    prompt = captured[0]
    assert "검색 범위를 좁혀" in prompt
    assert "다른 설명 방식" not in prompt


@pytest.mark.asyncio
async def test_curator_agent_prompt_changes_framing_on_low_relevancy_hint(monkeypatch):
    """hint='change_framing'(D26 — low_relevancy 재시도)면 카드 설명 방식을 바꾸라는 지시가 추가된다."""
    captured = _capture_curator_prompt(monkeypatch)

    await curator_agent(profile=make_profile(), issue=make_issue(), hint="change_framing")

    prompt = captured[0]
    assert "다른 설명 방식" in prompt
    assert "검색 범위를 좁혀" not in prompt


@pytest.mark.asyncio
async def test_curator_agent_uses_curator_model(monkeypatch):
    """gemini-2.5-flash(D22/D27 — 저비용 모델)로 GenerativeModel을 생성한다."""
    captured_model_names: list[str] = []

    class FakeGenerativeModel:
        def __init__(self, model_name, *_args, **_kwargs):
            captured_model_names.append(model_name)

        async def generate_content_async(self, _prompt, **_kwargs):
            return SimpleNamespace(text=json.dumps(FIXED_INSTRUCTION))

    monkeypatch.setattr(curator_agent_module.genai, "GenerativeModel", FakeGenerativeModel)

    await curator_agent(profile=make_profile(), issue=make_issue())

    assert captured_model_names == ["gemini-2.5-flash"]
