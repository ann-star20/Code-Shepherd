"""T2 파이프라인 단위 테스트 — RAG 검색 + 카드 생성 (Mock 기반, 실 DB/LLM 없이)."""

import asyncio
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from langsmith import traceable
from langsmith.run_helpers import get_current_run_tree, tracing_context

from app.kms.search_adapter import SearchAdapter, build_search1_text, build_search2_text, rag_search
from app.models.review_issue import ReviewIssue
from app.pipeline import learn_pipeline
from app.pipeline.curator_agent import DeveloperProfile


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


def make_doc(content: str) -> dict:
    return {"content": content, "metadata": {"category": "x"}, "similarity": 0.9}


class FakeAdapter(SearchAdapter):
    """search() 호출마다 미리 정해둔 결과를 순서대로 반환하는 테스트 더블."""

    def __init__(self, results_by_call: list[list[dict]]):
        self._results = list(results_by_call)
        self.calls: list[dict] = []

    async def search(self, embedding, category=None, limit=5):
        self.calls.append({"embedding": embedding, "category": category, "limit": limit})
        return self._results.pop(0)


FIXED_CARD = {
    "explanation": "SQL Injection은 사용자 입력을 검증 없이 쿼리에 삽입할 때 발생합니다.",
    "core_summary": "항상 파라미터 바인딩을 사용하세요.",
    "after_code": (
        "def search_products(keyword):\n"
        "    return db.execute(text('SELECT * FROM products WHERE name LIKE :kw'), {'kw': f'%{keyword}%'})"
    ),
    "recommendations": ["OWASP SQL Injection Prevention Cheat Sheet"],
}

FALLBACK_CARD = {
    "explanation": "RAG 컨텍스트 없이 LLM 자체 지식만으로 생성된 SQL Injection 설명입니다.",
    "core_summary": "사용자 입력은 항상 파라미터 바인딩으로 처리하세요.",
    "after_code": None,
    "recommendations": ["OWASP Top 10 — Injection"],
}

PASSED_RESULT = {"passed": True, "reason": None}
FAILED_RESULT = {"passed": False, "reason": None}
FAILED_RESULT_LOW_FAITHFULNESS = {"passed": False, "reason": "low_faithfulness"}
FAILED_RESULT_LOW_RELEVANCY = {"passed": False, "reason": "low_relevancy"}

FIXED_CURATOR_INSTRUCTION = {
    "depth": "deep",
    "focus": "파라미터 바인딩 vs 문자열 포매팅의 차이",
    "analogy": "자물쇠에 맞는 열쇠를 매번 새로 깎지 않고 마스터키 틀에 끼워 쓰는 것",
    "key_points": ["사용자 입력은 절대 쿼리 문자열에 직접 삽입하지 않는다"],
    "card_type": "code_fix",
    "query_fields": {
        "보안": "SQL Injection 방지 가이드",
        "코딩컨벤션": "파라미터 바인딩 코딩 컨벤션",
        "코드성능검증": "SQL Injection 학습 자료",
    },
}

RETRY_CURATOR_INSTRUCTION = {
    **FIXED_CURATOR_INSTRUCTION,
    "query_fields": {
        "보안": "SQL Injection 방지 가이드 (재검색)",
        "코딩컨벤션": "파라미터 바인딩 코딩 컨벤션 (재검색)",
        "코드성능검증": "SQL Injection 학습 자료 (재검색)",
    },
}

# mock_build_card가 모든 테스트에서 learn_pipeline.build_card를 패치하므로(autouse),
# 패치 전에 원본 함수를 잡아둬야 build_card 자체의 프롬프트 구성 로직을 테스트할 수 있다.
_REAL_BUILD_CARD = learn_pipeline.build_card

# mock_ragas_eval가 모든 테스트에서 learn_pipeline.ragas_eval을 패치하므로(autouse),
# 패치 전에 원본 함수를 잡아둬야 ragas_eval 자체의 구현(병렬 채점 등)을 테스트할 수 있다.
_REAL_RAGAS_EVAL = learn_pipeline.ragas_eval


@pytest.fixture(autouse=True)
def mock_embed_query():
    with patch.object(learn_pipeline, "embed_query", new=AsyncMock(return_value=[0.1] * 1024)) as mocked:
        yield mocked


@pytest.fixture(autouse=True)
def mock_build_card():
    with patch.object(learn_pipeline, "build_card", new=AsyncMock(return_value=dict(FIXED_CARD))) as mocked:
        yield mocked


@pytest.fixture(autouse=True)
def mock_ragas_eval():
    """기본은 1차 시도 통과 — 실패 시나리오를 검증하는 테스트에서만 side_effect로 덮어쓴다."""
    with patch.object(learn_pipeline, "ragas_eval", new=AsyncMock(return_value=dict(PASSED_RESULT))) as mocked:
        yield mocked


@pytest.fixture(autouse=True)
def mock_fallback_card():
    with patch.object(learn_pipeline, "fallback_card", new=AsyncMock(return_value=dict(FALLBACK_CARD))) as mocked:
        yield mocked


@pytest.fixture(autouse=True)
def mock_curator_agent():
    """기본은 매 호출마다 동일한 FIXED_CURATOR_INSTRUCTION 반환 — D26 재시도 흐름을 검증하는
    테스트에서만 side_effect로 1차/재시도 호출의 query_fields를 다르게 덮어쓴다."""
    with patch.object(learn_pipeline, "curator_agent", new=AsyncMock(return_value=dict(FIXED_CURATOR_INSTRUCTION))) as mocked:
        yield mocked


@pytest.mark.asyncio
async def test_build_card_success_returns_completed_plan(mock_build_card):
    issue = make_issue()
    adapter = FakeAdapter([
        [make_doc("security_guide doc 1"), make_doc("security_guide doc 2")],
        [make_doc("coding_convention doc 1"), make_doc("coding_convention doc 2")],
        [make_doc("learning_resource doc 1"), make_doc("learning_resource doc 2")],
    ])

    plan = await learn_pipeline.generate_card(issue, adapter)

    assert plan.issue_id == issue.id
    assert plan.status == "completed"
    assert plan.llm_fallback is False
    assert plan.error_message is None
    assert plan.card_content["before_code"] == issue.code_snippet
    assert plan.card_content["explanation"] == FIXED_CARD["explanation"]
    mock_build_card.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_card_uses_curator_query_fields_for_rag_search(mock_embed_query, mock_curator_agent):
    """generate_card는 D15의 고정 검색어(build_search1/2/3_text) 대신 curator_agent가 정한
    query_fields(보안/코딩컨벤션/코드성능검증)를 RAG 검색어로 사용한다 (T13/D22 — D15 룰 대체)."""
    issue = make_issue()
    adapter = FakeAdapter([
        [make_doc("security_guide doc 1"), make_doc("security_guide doc 2")],
        [make_doc("coding_convention doc 1"), make_doc("coding_convention doc 2")],
        [make_doc("learning_resource doc 1"), make_doc("learning_resource doc 2")],
    ])

    await learn_pipeline.generate_card(issue, adapter)

    query_fields = FIXED_CURATOR_INSTRUCTION["query_fields"]
    called_texts = [call.args[0] for call in mock_embed_query.await_args_list]
    assert called_texts == [query_fields["보안"], query_fields["코딩컨벤션"], query_fields["코드성능검증"]]


@pytest.mark.asyncio
async def test_generate_card_routes_concept_docs_to_performance_category_when_security_is_fallback(mock_curator_agent):
    """query_fields["보안"]이 D15 fallback(build_search1_text)과 동일하면 — Gemini가 "이 이슈는
    보안과 무관"이라고 판단해 비워둔 것 — "개념 설명" 참고자료(docs_concept)는 "보안" 대신
    "코드성능검증" 카테고리에서, query_fields["코드성능검증"]의 임베딩으로 검색한다 (D37)."""
    issue = make_issue()
    security_embedding = [0.1] * 1024
    performance_embedding = [0.3] * 1024
    embeddings_by_text = {
        build_search1_text(issue): security_embedding,
        "파라미터 바인딩 코딩 컨벤션": [0.2] * 1024,
        "시간복잡도 최적화 가이드": performance_embedding,
    }
    instruction = {
        **FIXED_CURATOR_INSTRUCTION,
        "query_fields": {
            "보안": build_search1_text(issue),  # D15 fallback 적용 = Gemini가 비워뒀다는 신호
            "코딩컨벤션": "파라미터 바인딩 코딩 컨벤션",
            "코드성능검증": "시간복잡도 최적화 가이드",
        },
    }
    mock_curator_agent.return_value = instruction

    async def fake_embed_query(text):
        return embeddings_by_text[text]

    adapter = FakeAdapter([
        [make_doc("performance concept doc 1"), make_doc("performance concept doc 2")],
        [make_doc("coding_convention doc 1"), make_doc("coding_convention doc 2")],
        [make_doc("performance recommend doc 1"), make_doc("performance recommend doc 2")],
    ])

    with patch.object(learn_pipeline, "embed_query", side_effect=fake_embed_query):
        await learn_pipeline.generate_card(issue, adapter)

    assert adapter.calls[0]["category"] == "코드성능검증"
    assert adapter.calls[0]["embedding"] == performance_embedding


@pytest.mark.asyncio
async def test_generate_card_routes_recommend_docs_to_security_category_when_performance_is_empty(mock_curator_agent):
    """query_fields["코드성능검증"]이 빈 문자열이면 — Gemini가 "이 이슈는 성능과 무관"이라고
    판단한 것이며 "코드성능검증"은 D15 fallback 대상이 아니라 빈 채로 남음 — "학습 추천"
    참고자료(docs_recommend)는 "코드성능검증" 대신 "보안" 카테고리에서, query_fields["보안"]의
    임베딩으로 검색한다 (D37)."""
    issue = make_issue()
    security_embedding = [0.1] * 1024
    embeddings_by_text = {
        "SQL Injection 방지 가이드": security_embedding,
        "파라미터 바인딩 코딩 컨벤션": [0.2] * 1024,
        "": [0.0] * 1024,
    }
    instruction = {
        **FIXED_CURATOR_INSTRUCTION,
        "query_fields": {
            "보안": "SQL Injection 방지 가이드",
            "코딩컨벤션": "파라미터 바인딩 코딩 컨벤션",
            "코드성능검증": "",  # Gemini가 비워둠 (fallback 없음)
        },
    }
    mock_curator_agent.return_value = instruction

    async def fake_embed_query(text):
        return embeddings_by_text[text]

    adapter = FakeAdapter([
        [make_doc("security concept doc 1"), make_doc("security concept doc 2")],
        [make_doc("coding_convention doc 1"), make_doc("coding_convention doc 2")],
        [make_doc("security recommend doc 1"), make_doc("security recommend doc 2")],
    ])

    with patch.object(learn_pipeline, "embed_query", side_effect=fake_embed_query):
        await learn_pipeline.generate_card(issue, adapter)

    assert adapter.calls[2]["category"] == "보안"
    assert adapter.calls[2]["embedding"] == security_embedding


@pytest.mark.asyncio
async def test_generate_card_embeds_query_fields_concurrently(mock_curator_agent):
    """query_fields(보안/코딩컨벤션/코드성능검증) 3개의 embed_query 호출은 asyncio.gather로
    동시에 실행되어, 지연시간이 합산이 아닌 최대값이 되어야 한다."""
    issue = make_issue()
    adapter = FakeAdapter([
        [make_doc("d1"), make_doc("d2")],
        [make_doc("d3"), make_doc("d4")],
        [make_doc("d5"), make_doc("d6")],
    ])

    in_flight = 0
    max_in_flight = 0

    async def fake_embed_query(_text):
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0)
        in_flight -= 1
        return [0.1] * 1024

    with patch.object(learn_pipeline, "embed_query", side_effect=fake_embed_query):
        await learn_pipeline.generate_card(issue, adapter)

    assert max_in_flight == 3


@pytest.mark.asyncio
async def test_generate_card_passes_curator_instruction_to_build_card(mock_build_card, mock_curator_agent):
    """generate_card는 curator_agent가 만든 curator_instruction(D22)을 build_card에 그대로 전달한다 (T14/D23, additive)."""
    issue = make_issue()
    adapter = FakeAdapter([
        [make_doc("security_guide doc 1"), make_doc("security_guide doc 2")],
        [make_doc("coding_convention doc 1"), make_doc("coding_convention doc 2")],
        [make_doc("learning_resource doc 1"), make_doc("learning_resource doc 2")],
    ])

    await learn_pipeline.generate_card(issue, adapter)

    assert mock_build_card.call_args.kwargs["curator_instruction"] == FIXED_CURATOR_INSTRUCTION


@pytest.mark.asyncio
async def test_generate_card_calls_curator_agent_with_profile_and_issue(mock_curator_agent):
    """generate_card는 호출자가 넘긴 profile(D22 DeveloperProfile)을 curator_agent에 그대로 전달한다."""
    issue = make_issue()
    adapter = FakeAdapter([
        [make_doc("d1"), make_doc("d2")],
        [make_doc("d3"), make_doc("d4")],
        [make_doc("d5"), make_doc("d6")],
    ])
    profile: DeveloperProfile = {"weak_categories": ["input validation"], "past_mistakes": ["SQL Injection"]}

    await learn_pipeline.generate_card(issue, adapter, profile=profile)

    assert mock_curator_agent.call_args.kwargs["profile"] == profile
    assert mock_curator_agent.call_args.kwargs["issue"] is issue


@pytest.mark.asyncio
async def test_generate_card_defaults_to_empty_profile_when_not_given(mock_curator_agent):
    """profile을 안 넘기면 빈 프로필(weak_categories/past_mistakes=[])로 curator_agent를 호출한다."""
    issue = make_issue()
    adapter = FakeAdapter([
        [make_doc("d1"), make_doc("d2")],
        [make_doc("d3"), make_doc("d4")],
        [make_doc("d5"), make_doc("d6")],
    ])

    await learn_pipeline.generate_card(issue, adapter)

    assert mock_curator_agent.call_args.kwargs["profile"] == {"weak_categories": [], "past_mistakes": []}


@pytest.mark.asyncio
async def test_rag_retries_without_domain_when_results_empty():
    adapter = FakeAdapter([
        [],  # 1차: category 필터 적용 → 결과 0개 (2개 미만)
        [make_doc("fallback doc 1"), make_doc("fallback doc 2")],  # 재시도: category=None → 2개
    ])

    docs = await rag_search(adapter, embedding=[0.1] * 1024, category="security_guide")

    assert len(adapter.calls) == 2
    assert adapter.calls[0]["category"] == "security_guide"
    assert adapter.calls[1]["category"] is None  # D15: domain(category) 제거 후 재시도
    assert docs is not None
    assert len(docs) == 2


@pytest.mark.asyncio
async def test_pgvector_empty_result_triggers_fallback():
    adapter = FakeAdapter([
        [],  # 1차: category 필터 → 0개
        [],  # 재시도: category=None → 그래도 0개
    ])

    docs = await rag_search(adapter, embedding=[0.1] * 1024, category="coding_convention")

    assert docs is None  # → LLM 자체 생성 fallback 신호
    assert len(adapter.calls) == 2


@pytest.mark.asyncio
async def test_embed_query_api_timeout_stores_error_message(mock_embed_query):
    mock_embed_query.side_effect = httpx.TimeoutException("Ollama embedding request timed out")
    issue = make_issue()
    adapter = FakeAdapter([])

    plan = await learn_pipeline.generate_card(issue, adapter)

    assert plan.status == "failed"
    assert plan.error_message is not None
    assert "timeout" in plan.error_message.lower()
    assert plan.card_content is None
    assert adapter.calls == []  # 임베딩 단계에서 실패 → RAG 검색까지 가지 않음


@pytest.mark.asyncio
async def test_build_card_without_code_snippet_uses_metadata_rag():
    issue = make_issue(code_snippet=None, name_of_function="process_payment")
    adapter = FakeAdapter([
        [make_doc("security_guide doc 1"), make_doc("security_guide doc 2")],
        [make_doc("coding_convention doc 1"), make_doc("coding_convention doc 2")],
        [make_doc("learning_resource doc 1"), make_doc("learning_resource doc 2")],
    ])

    plan = await learn_pipeline.generate_card(issue, adapter)

    search2_text = build_search2_text(issue)
    assert "code_snippet" not in search2_text  # code_snippet 없음 → metadata 기반 쿼리로 대체
    assert "keyword: SQL Injection" in search2_text
    assert "language: Python" in search2_text

    assert plan.card_content["before_code"] is None


def test_depth_is_deep_when_severity_critical():
    """severity=critical이면 depth가 'deep'으로 결정된다 (D18)."""
    issue = make_issue(severity="critical")
    assert learn_pipeline.determine_depth(issue) == "deep"


def test_depth_is_deep_when_severity_high():
    """severity=high이면 depth가 'deep'으로 결정된다 (D18, T10 확인 기준)."""
    issue = make_issue(severity="high")
    assert learn_pipeline.determine_depth(issue) == "deep"


def test_depth_is_quick_when_severity_low_and_mistake_count_below_threshold():
    """severity가 낮고 mistake_count가 3 미만이면 depth가 'quick'으로 결정된다 (D18, T10 확인 기준)."""
    issue = make_issue(severity="low")
    assert learn_pipeline.determine_depth(issue, mistake_count=2) == "quick"


@pytest.mark.asyncio
async def test_generate_card_forwards_mistake_count_to_depth_decision(mock_build_card):
    """generate_card가 받은 mistake_count를 determine_depth에 그대로 전달해 depth를 결정한다 (D18) —
    호출부에서 mistake_count를 안 넘기면 항상 0으로 처리되어 반복 실수 조건이 작동하지 않는 누락을 방지."""
    issue = make_issue(severity="low")
    adapter = FakeAdapter([
        [make_doc("security_guide doc 1"), make_doc("security_guide doc 2")],
        [make_doc("coding_convention doc 1"), make_doc("coding_convention doc 2")],
        [make_doc("learning_resource doc 1"), make_doc("learning_resource doc 2")],
    ])

    await learn_pipeline.generate_card(issue, adapter, mistake_count=3)

    assert mock_build_card.call_args.kwargs["depth"] == "deep"


def test_depth_is_deep_when_mistake_count_reaches_threshold():
    """severity가 낮아도 mistake_count가 3 이상이면 depth가 'deep'으로 결정된다 (D18)."""
    issue = make_issue(severity="low")
    assert learn_pipeline.determine_depth(issue, mistake_count=3) == "deep"


def _capture_builder_prompt(monkeypatch) -> list[str]:
    """genai.GenerativeModel을 대체해 build_card가 실제로 구성한 프롬프트 문자열을 캡처한다."""
    captured: list[str] = []

    class FakeGenerativeModel:
        def __init__(self, *_args, **_kwargs):
            pass

        async def generate_content_async(self, prompt, **_kwargs):
            captured.append(prompt)
            return SimpleNamespace(text=json.dumps(FIXED_CARD))

    monkeypatch.setattr(learn_pipeline.genai, "GenerativeModel", FakeGenerativeModel)
    return captured


@pytest.mark.asyncio
async def test_build_card_uses_deep_prompt_template_when_depth_is_deep(monkeypatch):
    """depth='deep'이면 DEEP_CARD_PROMPT(심화 학습 지시) 템플릿으로 프롬프트를 구성한다 (T10)."""
    captured = _capture_builder_prompt(monkeypatch)
    issue = make_issue(severity="critical")

    await _REAL_BUILD_CARD(
        issue=issue,
        docs_concept=None,
        docs_example=None,
        docs_recommend=None,
        depth="deep",
        card_type="concept",
    )

    assert len(captured) == 1
    assert "심화 학습용" in captured[0]
    assert "빠른 확인용" not in captured[0]


@pytest.mark.asyncio
async def test_build_card_uses_quick_prompt_template_when_depth_is_quick(monkeypatch):
    """depth='quick'이면 QUICK_CARD_PROMPT(간결 요약 지시) 템플릿으로 프롬프트를 구성한다 (T10)."""
    captured = _capture_builder_prompt(monkeypatch)
    issue = make_issue(severity="low")

    await _REAL_BUILD_CARD(
        issue=issue,
        docs_concept=None,
        docs_example=None,
        docs_recommend=None,
        depth="quick",
        card_type="concept",
    )

    assert len(captured) == 1
    assert "빠른 확인용" in captured[0]
    assert "심화 학습용" not in captured[0]


@pytest.mark.asyncio
async def test_build_card_includes_curator_guidance_when_provided(monkeypatch):
    """curator_instruction(D22)이 주어지면 focus/analogy/key_points를 프롬프트에 추가 지시로 포함한다 (T14/D23, additive)."""
    captured = _capture_builder_prompt(monkeypatch)
    issue = make_issue()

    await _REAL_BUILD_CARD(
        issue=issue,
        docs_concept=None,
        docs_example=None,
        docs_recommend=None,
        depth="deep",
        card_type="concept",
        curator_instruction=FIXED_CURATOR_INSTRUCTION,
    )

    assert FIXED_CURATOR_INSTRUCTION["focus"] in captured[0]
    assert FIXED_CURATOR_INSTRUCTION["analogy"] in captured[0]
    assert FIXED_CURATOR_INSTRUCTION["key_points"][0] in captured[0]


@pytest.mark.asyncio
async def test_build_card_without_curator_instruction_omits_curator_guidance(monkeypatch):
    """curator_instruction을 안 넘기면(기존 호출 — 하위 호환) Curator 지시 없이 프롬프트를 구성한다 (T14/D23, additive)."""
    captured = _capture_builder_prompt(monkeypatch)
    issue = make_issue()

    await _REAL_BUILD_CARD(
        issue=issue,
        docs_concept=None,
        docs_example=None,
        docs_recommend=None,
        depth="deep",
        card_type="concept",
    )

    assert FIXED_CURATOR_INSTRUCTION["focus"] not in captured[0]
    assert "Curator 지시" not in captured[0]


@pytest.mark.asyncio
async def test_build_card_includes_code_context_and_sub_category(monkeypatch):
    """code_context/sub_category를 Builder 프롬프트에 포함해 after_code 등 생성 시 참고하게 한다 (additive)."""
    captured = _capture_builder_prompt(monkeypatch)
    issue = make_issue()

    await _REAL_BUILD_CARD(
        issue=issue,
        docs_concept=None,
        docs_example=None,
        docs_recommend=None,
        depth="deep",
        card_type="concept",
    )

    assert issue.code_context in captured[0]
    assert issue.sub_category in captured[0]


@pytest.mark.asyncio
async def test_build_card_with_null_code_context_and_sub_category_uses_placeholder(monkeypatch):
    """code_context/sub_category가 null이면 "(없음)" placeholder로 대체한다 (additive)."""
    captured = _capture_builder_prompt(monkeypatch)
    issue = make_issue(code_context=None, sub_category=None)

    await _REAL_BUILD_CARD(
        issue=issue,
        docs_concept=None,
        docs_example=None,
        docs_recommend=None,
        depth="deep",
        card_type="concept",
    )

    assert "(없음)" in captured[0]


@pytest.mark.asyncio
async def test_build_card_prompt_instructs_learning_recommendations_tied_to_code_pattern(monkeypatch):
    """learning_recommendations 지시문은 리뷰 대상 코드의 구체적인 메서드/패턴과 연결해 추천하도록
    Builder에게 요구해야 한다 — 동일 keyword/sub_category의 두 이슈가 서로 다른 코드를 가져도
    학습 추천이 거의 동일하게 생성되는 문제를 줄이기 위함."""
    captured = _capture_builder_prompt(monkeypatch)
    issue = make_issue()

    await _REAL_BUILD_CARD(
        issue=issue,
        docs_concept=None,
        docs_example=None,
        docs_recommend=None,
        depth="deep",
        card_type="code_fix",
    )

    assert "리뷰 대상 코드의 구체적인 문제(예: 어떤 메서드/패턴을 썼는지)와 연결해서 추천해줘" in captured[0]


@pytest.mark.asyncio
async def test_build_card_raises_timeout_error_when_gemini_hangs(monkeypatch):
    """Gemini 호출이 응답 없이 멈추면 GEMINI_TIMEOUT_SECONDS 후 TimeoutError를 던진다 — curator_agent와
    동일한 이유로, 그렇지 않으면 background task(_run_card_generation)가 예외 없이 멈춰 plan이
    error_message=None인 채 status='running'에 영구히 남는다 (재생성 중 실제로 발생한 버그)."""
    monkeypatch.setattr(learn_pipeline, "GEMINI_TIMEOUT_SECONDS", 0.05)

    class HangingGenerativeModel:
        def __init__(self, *_args, **_kwargs):
            pass

        async def generate_content_async(self, _prompt, **_kwargs):
            await asyncio.sleep(10)

    monkeypatch.setattr(learn_pipeline.genai, "GenerativeModel", HangingGenerativeModel)
    issue = make_issue()

    with pytest.raises(TimeoutError):
        await _REAL_BUILD_CARD(
            issue=issue,
            docs_concept=None,
            docs_example=None,
            docs_recommend=None,
            depth="quick",
            card_type="concept",
        )


@pytest.mark.parametrize(
    ("faithfulness_score", "relevancy_score", "expected_reason"),
    [
        (0.9, 0.9, None),
        (0.5, 0.9, "low_faithfulness"),
        (0.9, 0.5, "low_relevancy"),
        (0.5, 0.5, "low_faithfulness"),  # faithfulness 미달이 relevancy보다 우선
    ],
)
def test_ragas_reason_classifies_failure_cause(faithfulness_score, relevancy_score, expected_reason):
    """_ragas_reason — faithfulness 미달을 relevancy 미달보다 우선 분류한다 (T12/D14, D26 재시도 힌트 분기용)."""
    assert learn_pipeline._ragas_reason(faithfulness_score, relevancy_score) == expected_reason


@pytest.mark.asyncio
async def test_ragas_eval_scores_faithfulness_and_relevancy_concurrently():
    """ragas_eval()은 faithfulness/answer_relevancy 채점을 asyncio.gather로 동시 실행해야 한다 (지연시간 최적화).

    각 채점에 DELAY초가 걸리도록 mock하면, 순차 실행은 ~2*DELAY초, 병렬 실행은 ~DELAY초가 걸린다.
    """
    # ragas_eval()의 local import(ragas/langchain_google_genai 등)는 최초 1회 로딩이 수십 초 걸려서,
    # 측정 구간 안에 들어가면 DELAY 차이를 가려버린다 — 타이머 시작 전에 미리 import해 캐싱한다.
    import ragas.embeddings  # noqa: F401
    import ragas.llms  # noqa: F401
    import ragas.metrics  # noqa: F401
    import langchain_google_genai  # noqa: F401

    DELAY = 0.1

    async def slow_score(_sample):
        await asyncio.sleep(DELAY)
        return 0.9

    with (
        patch("ragas.metrics.faithfulness") as mock_faithfulness,
        patch("ragas.metrics.answer_relevancy") as mock_relevancy,
        patch("ragas.llms.LangchainLLMWrapper"),
        patch("ragas.embeddings.LangchainEmbeddingsWrapper"),
        patch("langchain_google_genai.ChatGoogleGenerativeAI"),
        patch("langchain_google_genai.GoogleGenerativeAIEmbeddings"),
    ):
        mock_faithfulness.single_turn_ascore = AsyncMock(side_effect=slow_score)
        mock_relevancy.single_turn_ascore = AsyncMock(side_effect=slow_score)

        start = asyncio.get_event_loop().time()
        result = await _REAL_RAGAS_EVAL({"explanation": "exp", "core_summary": "sum"}, [make_doc("doc")])
        elapsed = asyncio.get_event_loop().time() - start

    assert result == {"passed": True, "reason": None}
    assert elapsed < DELAY * 1.5  # 병렬이면 ~DELAY초, 순차면 ~2*DELAY초라 1.5*DELAY를 넘는다


@pytest.mark.asyncio
async def test_ragas_eval_raises_timeout_error_when_judge_llm_hangs(monkeypatch):
    """RAGAS judge LLM(faithfulness/answer_relevancy) 호출이 응답 없이 멈추면 GEMINI_TIMEOUT_SECONDS 후
    TimeoutError를 던져야 한다 — build_card와 동일한 이유로, 그렇지 않으면 AgentHarness의 360초
    타임아웃(GEMINI_TIMEOUT_SECONDS*2*3)까지 기다린 뒤 error_message=''인 채 status='failed'로
    남는다 (재생성 중 실제로 발생한 버그)."""
    import ragas.embeddings  # noqa: F401
    import ragas.llms  # noqa: F401
    import ragas.metrics  # noqa: F401
    import langchain_google_genai  # noqa: F401

    monkeypatch.setattr(learn_pipeline, "GEMINI_TIMEOUT_SECONDS", 0.05)

    async def hanging_score(_sample):
        await asyncio.sleep(10)
        return 0.9

    with (
        patch("ragas.metrics.faithfulness") as mock_faithfulness,
        patch("ragas.metrics.answer_relevancy") as mock_relevancy,
        patch("ragas.llms.LangchainLLMWrapper"),
        patch("ragas.embeddings.LangchainEmbeddingsWrapper"),
        patch("langchain_google_genai.ChatGoogleGenerativeAI"),
        patch("langchain_google_genai.GoogleGenerativeAIEmbeddings"),
    ):
        mock_faithfulness.single_turn_ascore = AsyncMock(side_effect=hanging_score)
        mock_relevancy.single_turn_ascore = AsyncMock(side_effect=hanging_score)

        with pytest.raises(TimeoutError):
            await _REAL_RAGAS_EVAL({"explanation": "exp", "core_summary": "sum"}, [make_doc("doc")])


def test_format_docs_includes_parent_content_as_context():
    """_format_docs는 각 문서의 parent_content(부모 chunk 컨텍스트)를 함께 포함해 Builder에게
    더 넓은 맥락을 제공한다 (RAG 검색 갭 백로그 — Child 정밀검색 + Parent 컨텍스트 보강)."""
    docs = [{"content": "child text", "metadata": {}, "similarity": 0.9, "parent_content": "parent context"}]

    formatted = learn_pipeline._format_docs(docs)

    assert "child text" in formatted
    assert "parent context" in formatted


def test_format_docs_without_parent_content_unchanged():
    """parent_content가 없는 문서(기존 동작)는 child content만 포함된다."""
    formatted = learn_pipeline._format_docs([make_doc("child only")])

    assert formatted == "- child only"


@pytest.mark.asyncio
async def test_ragas_eval_retrieved_contexts_includes_parent_content():
    """ragas_eval()의 retrieved_contexts에 각 문서의 parent_content도 포함해, build_card에게 전달한
    맥락과 동일한 근거로 faithfulness를 평가한다 (RAG 검색 갭 백로그)."""
    docs = [
        {"content": "child1", "metadata": {}, "similarity": 0.9, "parent_content": "parent1"},
        {"content": "child2", "metadata": {}, "similarity": 0.8, "parent_content": None},
    ]

    async def fake_score(_sample):
        return 0.9

    with (
        patch("ragas.SingleTurnSample") as mock_sample_cls,
        patch("ragas.metrics.faithfulness") as mock_faithfulness,
        patch("ragas.metrics.answer_relevancy") as mock_relevancy,
        patch("ragas.llms.LangchainLLMWrapper"),
        patch("ragas.embeddings.LangchainEmbeddingsWrapper"),
        patch("langchain_google_genai.ChatGoogleGenerativeAI"),
        patch("langchain_google_genai.GoogleGenerativeAIEmbeddings"),
    ):
        mock_faithfulness.single_turn_ascore = AsyncMock(side_effect=fake_score)
        mock_relevancy.single_turn_ascore = AsyncMock(side_effect=fake_score)

        await _REAL_RAGAS_EVAL({"explanation": "exp", "core_summary": "sum"}, docs)

    assert mock_sample_cls.call_args.kwargs["retrieved_contexts"] == ["child1", "parent1", "child2"]


@pytest.mark.asyncio
async def test_ragas_all_3_fail_triggers_llm_fallback(
    mock_ragas_eval, mock_fallback_card, mock_build_card, mock_curator_agent
):
    """RAGAS 평가가 3회 모두 실패하면 fallback_card()로 대체하고 llm_fallback=True가 된다 (T3).

    3번째 시도 실패 후에는 더 이상 재시도가 없으므로 curator_agent 재호출도 일어나지 않는다 —
    초기 1회 + 1·2차 실패 후 재시도 2회 = 총 3회 (T13/D26)."""
    mock_ragas_eval.side_effect = [
        dict(FAILED_RESULT_LOW_FAITHFULNESS),
        dict(FAILED_RESULT_LOW_FAITHFULNESS),
        dict(FAILED_RESULT_LOW_FAITHFULNESS),
    ]
    issue = make_issue()
    adapter = FakeAdapter([
        [make_doc("security_guide doc 1"), make_doc("security_guide doc 2")],
        [make_doc("coding_convention doc 1"), make_doc("coding_convention doc 2")],
        [make_doc("learning_resource doc 1"), make_doc("learning_resource doc 2")],
        [make_doc("retry1 security_guide doc 1"), make_doc("retry1 security_guide doc 2")],
        [make_doc("retry1 coding_convention doc 1"), make_doc("retry1 coding_convention doc 2")],
        [make_doc("retry1 learning_resource doc 1"), make_doc("retry1 learning_resource doc 2")],
        [make_doc("retry2 security_guide doc 1"), make_doc("retry2 security_guide doc 2")],
        [make_doc("retry2 coding_convention doc 1"), make_doc("retry2 coding_convention doc 2")],
        [make_doc("retry2 learning_resource doc 1"), make_doc("retry2 learning_resource doc 2")],
    ])

    plan = await learn_pipeline.generate_card(issue, adapter)

    assert mock_ragas_eval.await_count == 3
    assert mock_build_card.await_count == 3
    assert mock_curator_agent.call_count == 3  # 초기 1회 + 1·2차 실패 후 재시도 2회
    mock_fallback_card.assert_awaited_once()
    assert plan.status == "completed"
    assert plan.llm_fallback is True
    assert plan.card_content["explanation"] == FALLBACK_CARD["explanation"]
    assert plan.card_content["before_code"] == issue.code_snippet
    assert plan.ragas_reason == "low_faithfulness"  # 마지막 시도의 실패 원인을 기록 (T12)


@pytest.mark.asyncio
async def test_ragas_passes_after_retry_stops_loop(
    mock_ragas_eval, mock_fallback_card, mock_build_card, mock_curator_agent
):
    """RAGAS 평가가 2번째 시도에 통과하면 즉시 루프를 멈추고 fallback은 호출하지 않는다 (T3)."""
    mock_ragas_eval.side_effect = [dict(FAILED_RESULT_LOW_FAITHFULNESS), dict(PASSED_RESULT)]
    issue = make_issue()
    adapter = FakeAdapter([
        [make_doc("security_guide doc 1"), make_doc("security_guide doc 2")],
        [make_doc("coding_convention doc 1"), make_doc("coding_convention doc 2")],
        [make_doc("learning_resource doc 1"), make_doc("learning_resource doc 2")],
        [make_doc("retry security_guide doc 1"), make_doc("retry security_guide doc 2")],
        [make_doc("retry coding_convention doc 1"), make_doc("retry coding_convention doc 2")],
        [make_doc("retry learning_resource doc 1"), make_doc("retry learning_resource doc 2")],
    ])

    plan = await learn_pipeline.generate_card(issue, adapter)

    assert mock_ragas_eval.await_count == 2
    assert mock_build_card.await_count == 2
    assert mock_curator_agent.call_count == 2  # 초기 1회 + 1차 실패 후 재시도 1회
    mock_fallback_card.assert_not_awaited()
    assert plan.llm_fallback is False
    assert plan.ragas_reason is None  # 마지막(통과한) 시도의 reason은 None (T12)


@pytest.mark.asyncio
async def test_ragas_eval_timeout_breaks_immediately_and_uses_rag_grounded_card_without_fallback(
    mock_ragas_eval, mock_fallback_card, mock_build_card, mock_curator_agent
):
    """RAGAS judge LLM이 응답 시간 초과(TimeoutError)면 재시도해도 같은 judge 호출을 다시 기다려야 해
    타임아웃이 반복될 가능성이 높으므로, low_faithfulness/low_relevancy와 달리 즉시 루프를 멈춘다.
    이때 card_content는 이미 RAG 문서(docs_concept/docs_example/docs_recommend)로 build_card()가
    만들어 둔 결과이므로 — RAGAS 검증(타임아웃)만 스킵하고 그 결과를 그대로 사용한다.
    fallback_card()(RAG 없이 LLM 자체 지식만 사용)는 호출하지 않아 learning_recommendations의
    RAG 기반 일관성을 유지한다."""
    mock_ragas_eval.side_effect = [
        TimeoutError("ragas_eval: RAGAS judge LLM 응답 시간 초과 (60s)"),
    ]
    issue = make_issue()
    adapter = FakeAdapter([
        [make_doc("security_guide doc 1"), make_doc("security_guide doc 2")],
        [make_doc("coding_convention doc 1"), make_doc("coding_convention doc 2")],
        [make_doc("learning_resource doc 1"), make_doc("learning_resource doc 2")],
    ])

    plan = await learn_pipeline.generate_card(issue, adapter)

    assert mock_ragas_eval.await_count == 1
    assert mock_build_card.await_count == 1
    assert mock_curator_agent.call_count == 1  # 재시도 없음 — curator_agent 추가 호출 없음
    mock_fallback_card.assert_not_awaited()
    assert plan.status == "completed"
    assert plan.llm_fallback is False
    assert plan.card_content["explanation"] == FIXED_CARD["explanation"]
    assert plan.ragas_reason == "ragas_timeout"
    assert plan.attempt_count == 1


@pytest.mark.asyncio
async def test_ragas_retry_calls_curator_with_narrow_query_hint_on_low_faithfulness(
    mock_ragas_eval, mock_embed_query, mock_curator_agent, mock_build_card
):
    """RAGAS 평가가 low_faithfulness로 실패하면 curator_agent(hint="narrow_query")를 재호출해
    새 query_fields로 RAG를 재검색한다 (T13/D26)."""
    mock_ragas_eval.side_effect = [dict(FAILED_RESULT_LOW_FAITHFULNESS), dict(PASSED_RESULT)]
    mock_curator_agent.side_effect = [dict(FIXED_CURATOR_INSTRUCTION), dict(RETRY_CURATOR_INSTRUCTION)]
    issue = make_issue()
    adapter = FakeAdapter([
        [make_doc("security_guide doc 1"), make_doc("security_guide doc 2")],
        [make_doc("coding_convention doc 1"), make_doc("coding_convention doc 2")],
        [make_doc("learning_resource doc 1"), make_doc("learning_resource doc 2")],
        [make_doc("retry security_guide doc 1"), make_doc("retry security_guide doc 2")],
        [make_doc("retry coding_convention doc 1"), make_doc("retry coding_convention doc 2")],
        [make_doc("retry learning_resource doc 1"), make_doc("retry learning_resource doc 2")],
    ])

    await learn_pipeline.generate_card(issue, adapter)

    assert mock_curator_agent.call_args_list[0].kwargs.get("hint") is None  # 초기 호출은 hint 없음
    assert mock_curator_agent.call_args_list[1].kwargs["hint"] == "narrow_query"

    retry_query_fields = RETRY_CURATOR_INSTRUCTION["query_fields"]
    called_texts = [call.args[0] for call in mock_embed_query.await_args_list]
    assert called_texts[3:] == [
        retry_query_fields["보안"],
        retry_query_fields["코딩컨벤션"],
        retry_query_fields["코드성능검증"],
    ]


@pytest.mark.asyncio
async def test_ragas_retry_calls_curator_with_change_framing_hint_on_low_relevancy(
    mock_ragas_eval, mock_embed_query, mock_curator_agent, mock_build_card
):
    """RAGAS 평가가 low_relevancy로 실패하면 curator_agent(hint="change_framing")를 재호출해
    새 query_fields로 RAG를 재검색한다 (T13/D26)."""
    mock_ragas_eval.side_effect = [dict(FAILED_RESULT_LOW_RELEVANCY), dict(PASSED_RESULT)]
    mock_curator_agent.side_effect = [dict(FIXED_CURATOR_INSTRUCTION), dict(RETRY_CURATOR_INSTRUCTION)]
    issue = make_issue()
    adapter = FakeAdapter([
        [make_doc("security_guide doc 1"), make_doc("security_guide doc 2")],
        [make_doc("coding_convention doc 1"), make_doc("coding_convention doc 2")],
        [make_doc("learning_resource doc 1"), make_doc("learning_resource doc 2")],
        [make_doc("retry security_guide doc 1"), make_doc("retry security_guide doc 2")],
        [make_doc("retry coding_convention doc 1"), make_doc("retry coding_convention doc 2")],
        [make_doc("retry learning_resource doc 1"), make_doc("retry learning_resource doc 2")],
    ])

    await learn_pipeline.generate_card(issue, adapter)

    assert mock_curator_agent.call_args_list[0].kwargs.get("hint") is None  # 초기 호출은 hint 없음
    assert mock_curator_agent.call_args_list[1].kwargs["hint"] == "change_framing"

    retry_query_fields = RETRY_CURATOR_INSTRUCTION["query_fields"]
    called_texts = [call.args[0] for call in mock_embed_query.await_args_list]
    assert called_texts[3:] == [
        retry_query_fields["보안"],
        retry_query_fields["코딩컨벤션"],
        retry_query_fields["코드성능검증"],
    ]


@pytest.mark.asyncio
async def test_generate_card_passes_retried_curator_instruction_to_build_card(
    mock_ragas_eval, mock_embed_query, mock_curator_agent, mock_build_card
):
    """RAGAS 재시도로 curator_instruction이 갱신되면, 다음 build_card 호출에는 갱신된
    curator_instruction을 전달한다 (T14/D23, additive)."""
    mock_ragas_eval.side_effect = [dict(FAILED_RESULT_LOW_FAITHFULNESS), dict(PASSED_RESULT)]
    mock_curator_agent.side_effect = [dict(FIXED_CURATOR_INSTRUCTION), dict(RETRY_CURATOR_INSTRUCTION)]
    issue = make_issue()
    adapter = FakeAdapter([
        [make_doc("security_guide doc 1"), make_doc("security_guide doc 2")],
        [make_doc("coding_convention doc 1"), make_doc("coding_convention doc 2")],
        [make_doc("learning_resource doc 1"), make_doc("learning_resource doc 2")],
        [make_doc("retry security_guide doc 1"), make_doc("retry security_guide doc 2")],
        [make_doc("retry coding_convention doc 1"), make_doc("retry coding_convention doc 2")],
        [make_doc("retry learning_resource doc 1"), make_doc("retry learning_resource doc 2")],
    ])

    await learn_pipeline.generate_card(issue, adapter)

    assert mock_build_card.call_args_list[0].kwargs["curator_instruction"] == FIXED_CURATOR_INSTRUCTION
    assert mock_build_card.call_args_list[1].kwargs["curator_instruction"] == RETRY_CURATOR_INSTRUCTION


@pytest.mark.asyncio
async def test_generate_card_passes_curator_instruction_to_fallback_card(
    mock_ragas_eval, mock_fallback_card, mock_build_card, mock_curator_agent
):
    """RAGAS 3회 모두 실패해 fallback_card()로 넘어갈 때도 마지막 curator_instruction을 전달한다 (T14/D23, additive)."""
    mock_ragas_eval.side_effect = [
        dict(FAILED_RESULT_LOW_FAITHFULNESS),
        dict(FAILED_RESULT_LOW_FAITHFULNESS),
        dict(FAILED_RESULT_LOW_FAITHFULNESS),
    ]
    issue = make_issue()
    adapter = FakeAdapter([
        [make_doc("security_guide doc 1"), make_doc("security_guide doc 2")],
        [make_doc("coding_convention doc 1"), make_doc("coding_convention doc 2")],
        [make_doc("learning_resource doc 1"), make_doc("learning_resource doc 2")],
        [make_doc("retry1 security_guide doc 1"), make_doc("retry1 security_guide doc 2")],
        [make_doc("retry1 coding_convention doc 1"), make_doc("retry1 coding_convention doc 2")],
        [make_doc("retry1 learning_resource doc 1"), make_doc("retry1 learning_resource doc 2")],
        [make_doc("retry2 security_guide doc 1"), make_doc("retry2 security_guide doc 2")],
        [make_doc("retry2 coding_convention doc 1"), make_doc("retry2 coding_convention doc 2")],
        [make_doc("retry2 learning_resource doc 1"), make_doc("retry2 learning_resource doc 2")],
    ])

    await learn_pipeline.generate_card(issue, adapter)

    assert mock_fallback_card.call_args.kwargs["curator_instruction"] == FIXED_CURATOR_INSTRUCTION


@pytest.mark.asyncio
async def test_generate_card_records_attempt_count_1_on_first_try_success(mock_curator_agent):
    """RAGAS가 1차 시도에 통과하면 attempt_count=1, curator_instruction은 초기 Curator 지시를 기록한다 (T16)."""
    issue = make_issue()
    adapter = FakeAdapter([
        [make_doc("security_guide doc 1"), make_doc("security_guide doc 2")],
        [make_doc("coding_convention doc 1"), make_doc("coding_convention doc 2")],
        [make_doc("learning_resource doc 1"), make_doc("learning_resource doc 2")],
    ])

    plan = await learn_pipeline.generate_card(issue, adapter)

    assert plan.attempt_count == 1
    assert plan.curator_instruction == FIXED_CURATOR_INSTRUCTION


@pytest.mark.asyncio
async def test_generate_card_records_attempt_count_2_after_one_retry(
    mock_ragas_eval, mock_embed_query, mock_curator_agent, mock_build_card
):
    """RAGAS가 2번째 시도에 통과하면 attempt_count=2, curator_instruction은 재시도로 갱신된 지시를 기록한다 (T16)."""
    mock_ragas_eval.side_effect = [dict(FAILED_RESULT_LOW_FAITHFULNESS), dict(PASSED_RESULT)]
    mock_curator_agent.side_effect = [dict(FIXED_CURATOR_INSTRUCTION), dict(RETRY_CURATOR_INSTRUCTION)]
    issue = make_issue()
    adapter = FakeAdapter([
        [make_doc("security_guide doc 1"), make_doc("security_guide doc 2")],
        [make_doc("coding_convention doc 1"), make_doc("coding_convention doc 2")],
        [make_doc("learning_resource doc 1"), make_doc("learning_resource doc 2")],
        [make_doc("retry security_guide doc 1"), make_doc("retry security_guide doc 2")],
        [make_doc("retry coding_convention doc 1"), make_doc("retry coding_convention doc 2")],
        [make_doc("retry learning_resource doc 1"), make_doc("retry learning_resource doc 2")],
    ])

    plan = await learn_pipeline.generate_card(issue, adapter)

    assert plan.attempt_count == 2
    assert plan.curator_instruction == RETRY_CURATOR_INSTRUCTION


@pytest.mark.asyncio
async def test_generate_card_records_attempt_count_3_on_fallback_after_3_failures(
    mock_ragas_eval, mock_fallback_card, mock_build_card, mock_curator_agent
):
    """RAGAS가 3회 모두 실패해 fallback_card로 대체되면 attempt_count=3을 기록한다 (T16)."""
    mock_ragas_eval.side_effect = [
        dict(FAILED_RESULT_LOW_FAITHFULNESS),
        dict(FAILED_RESULT_LOW_FAITHFULNESS),
        dict(FAILED_RESULT_LOW_FAITHFULNESS),
    ]
    issue = make_issue()
    adapter = FakeAdapter([
        [make_doc("security_guide doc 1"), make_doc("security_guide doc 2")],
        [make_doc("coding_convention doc 1"), make_doc("coding_convention doc 2")],
        [make_doc("learning_resource doc 1"), make_doc("learning_resource doc 2")],
        [make_doc("retry1 security_guide doc 1"), make_doc("retry1 security_guide doc 2")],
        [make_doc("retry1 coding_convention doc 1"), make_doc("retry1 coding_convention doc 2")],
        [make_doc("retry1 learning_resource doc 1"), make_doc("retry1 learning_resource doc 2")],
        [make_doc("retry2 security_guide doc 1"), make_doc("retry2 security_guide doc 2")],
        [make_doc("retry2 coding_convention doc 1"), make_doc("retry2 coding_convention doc 2")],
        [make_doc("retry2 learning_resource doc 1"), make_doc("retry2 learning_resource doc 2")],
    ])

    plan = await learn_pipeline.generate_card(issue, adapter)

    assert plan.attempt_count == 3


@pytest.mark.asyncio
async def test_generate_card_records_attempt_count_0_on_embed_query_timeout(mock_embed_query, mock_curator_agent):
    """embed_query 타임아웃으로 build_card 시도 자체가 없으면 attempt_count=0이고, curator_instruction은
    timeout 이전에 호출된 초기 Curator 지시를 기록한다 (T16)."""
    mock_embed_query.side_effect = httpx.TimeoutException("Ollama embedding request timed out")
    issue = make_issue()
    adapter = FakeAdapter([])

    plan = await learn_pipeline.generate_card(issue, adapter)

    assert plan.attempt_count == 0
    assert plan.curator_instruction == FIXED_CURATOR_INSTRUCTION


@pytest.mark.asyncio
async def test_docs_none_skips_ragas_and_sets_llm_fallback(mock_ragas_eval, mock_fallback_card, mock_build_card):
    """RAG 검색 결과가 없어 llm_fallback=True가 되면 RAGAS 평가 자체를 건너뛴다 (D4/D30)."""
    issue = make_issue()
    adapter = FakeAdapter([
        [],  # security_guide 1차 → 0개
        [],  # 재시도(category=None) → 그래도 0개 → docs_concept=None
        [make_doc("coding_convention doc 1"), make_doc("coding_convention doc 2")],
        [make_doc("learning_resource doc 1"), make_doc("learning_resource doc 2")],
    ])

    plan = await learn_pipeline.generate_card(issue, adapter)

    mock_ragas_eval.assert_not_awaited()
    mock_fallback_card.assert_not_awaited()
    mock_build_card.assert_awaited_once()
    assert plan.llm_fallback is True
    assert plan.status == "completed"
    assert plan.ragas_reason is None  # RAGAS 미실행 (T12)


@pytest.mark.asyncio
async def test_build_card_exception_returns_failed_plan_with_error_message(mock_build_card):
    """build_card() 호출 중 예외(Gemini API 오류, JSON 파싱 실패 등)가 나면 status='failed'로 기록한다 (T6)."""
    mock_build_card.side_effect = Exception("Gemini API 오류: 429 rate limit exceeded")
    issue = make_issue()
    adapter = FakeAdapter([
        [],  # security_guide 1차 → 0개
        [],  # 재시도(category=None) → 0개 → docs_concept=None → llm_fallback=True (build_card 단일 호출 경로)
        [make_doc("coding_convention doc 1"), make_doc("coding_convention doc 2")],
        [make_doc("learning_resource doc 1"), make_doc("learning_resource doc 2")],
    ])

    plan = await learn_pipeline.generate_card(issue, adapter)

    assert plan.status == "failed"
    assert plan.llm_fallback is False
    assert plan.error_message is not None
    assert "Gemini API 오류" in plan.error_message
    assert plan.card_content is None


@pytest.mark.asyncio
async def test_fallback_card_exception_returns_failed_plan_with_error_message(
    mock_ragas_eval, mock_fallback_card, mock_build_card
):
    """RAGAS 3회 실패 후 마지막 안전망인 fallback_card()마저 예외를 내면 status='failed'로 기록한다 (T6)."""
    mock_ragas_eval.side_effect = [dict(FAILED_RESULT), dict(FAILED_RESULT), dict(FAILED_RESULT)]
    mock_fallback_card.side_effect = Exception("Gemini API 오류: 503 service unavailable")
    issue = make_issue()
    adapter = FakeAdapter([
        [make_doc("security_guide doc 1"), make_doc("security_guide doc 2")],
        [make_doc("coding_convention doc 1"), make_doc("coding_convention doc 2")],
        [make_doc("learning_resource doc 1"), make_doc("learning_resource doc 2")],
        [make_doc("retry1 security_guide doc 1"), make_doc("retry1 security_guide doc 2")],
        [make_doc("retry1 coding_convention doc 1"), make_doc("retry1 coding_convention doc 2")],
        [make_doc("retry1 learning_resource doc 1"), make_doc("retry1 learning_resource doc 2")],
        [make_doc("retry2 security_guide doc 1"), make_doc("retry2 security_guide doc 2")],
        [make_doc("retry2 coding_convention doc 1"), make_doc("retry2 coding_convention doc 2")],
        [make_doc("retry2 learning_resource doc 1"), make_doc("retry2 learning_resource doc 2")],
    ])

    plan = await learn_pipeline.generate_card(issue, adapter)

    assert mock_build_card.await_count == 3  # RAGAS 3회 시도가 모두 실패한 뒤에 fallback 경로로 진입
    assert plan.status == "failed"
    assert plan.llm_fallback is False
    assert plan.error_message is not None
    assert "503" in plan.error_message
    assert plan.card_content is None


@pytest.mark.asyncio
async def test_skip_ragas_eval_flag_bypasses_loop(monkeypatch, mock_ragas_eval, mock_fallback_card, mock_build_card):
    """SKIP_RAGAS_EVAL=true면 RAG 결과가 충분해도 RAGAS 루프를 생략한다 (자체 cost-control 플래그)."""
    monkeypatch.setenv("SKIP_RAGAS_EVAL", "true")
    issue = make_issue()
    adapter = FakeAdapter([
        [make_doc("security_guide doc 1"), make_doc("security_guide doc 2")],
        [make_doc("coding_convention doc 1"), make_doc("coding_convention doc 2")],
        [make_doc("learning_resource doc 1"), make_doc("learning_resource doc 2")],
    ])

    plan = await learn_pipeline.generate_card(issue, adapter)

    mock_ragas_eval.assert_not_awaited()
    mock_fallback_card.assert_not_awaited()
    mock_build_card.assert_awaited_once()
    assert plan.llm_fallback is False
    assert plan.status == "completed"
    assert plan.ragas_reason is None  # RAGAS 미실행 (T12)


@pytest.mark.asyncio
async def test_generate_card_propagates_trace_id_to_nested_traceable_calls(
    mock_curator_agent, mock_build_card, mock_ragas_eval, mock_embed_query, mock_fallback_card
):
    """generate_card에 config={"metadata": {"trace_id": ...}}를 넘기면(AgentHarness.run()이 주입) —
    tracing_context로 전파되어 내부에서 호출되는 @traceable 함수(curator_agent 등)의 LangSmith
    run metadata에도 같은 trace_id가 기록된다. 이를 통해 LangSmith에서 trace_id로 카드 생성
    전체 과정(Curator 판단/RAG검색/카드생성/RAGAS평가)을 한 그룹으로 필터링할 수 있다."""
    captured_metadata: dict = {}

    @traceable(name="curator_agent")
    async def traced_curator_agent(**kwargs):
        run = get_current_run_tree()
        captured_metadata.update(run.extra.get("metadata", {}) if run else {})
        return dict(FIXED_CURATOR_INSTRUCTION)

    mock_curator_agent.side_effect = traced_curator_agent

    issue = make_issue()
    adapter = FakeAdapter([
        [make_doc("d1"), make_doc("d2")],
        [make_doc("d3"), make_doc("d4")],
        [make_doc("d5"), make_doc("d6")],
    ])
    config = {"metadata": {"trace_id": "pr_abc_generate_card_a1b2", "agent_name": "generate_card"}}

    fake_client = MagicMock()
    with tracing_context(enabled=True, client=fake_client):
        plan = await learn_pipeline.generate_card(issue, adapter, config=config)

    assert plan.status == "completed"
    assert captured_metadata.get("trace_id") == "pr_abc_generate_card_a1b2"
