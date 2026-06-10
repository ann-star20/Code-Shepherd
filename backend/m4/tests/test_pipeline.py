"""T2 파이프라인 단위 테스트 — RAG 검색 + 카드 생성 (Mock 기반, 실 DB/LLM 없이)."""

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.kms.search_adapter import SearchAdapter, build_search2_text, rag_search
from app.models.review_issue import ReviewIssue
from app.pipeline import learn_pipeline


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

# mock_build_card가 모든 테스트에서 learn_pipeline.build_card를 패치하므로(autouse),
# 패치 전에 원본 함수를 잡아둬야 build_card 자체의 프롬프트 구성 로직을 테스트할 수 있다.
_REAL_BUILD_CARD = learn_pipeline.build_card


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
async def test_ragas_all_3_fail_triggers_llm_fallback(mock_ragas_eval, mock_fallback_card, mock_build_card):
    """RAGAS 평가가 3회 모두 실패하면 fallback_card()로 대체하고 llm_fallback=True가 된다 (T3)."""
    mock_ragas_eval.side_effect = [dict(FAILED_RESULT), dict(FAILED_RESULT), dict(FAILED_RESULT)]
    issue = make_issue()
    adapter = FakeAdapter([
        [make_doc("security_guide doc 1"), make_doc("security_guide doc 2")],
        [make_doc("coding_convention doc 1"), make_doc("coding_convention doc 2")],
        [make_doc("learning_resource doc 1"), make_doc("learning_resource doc 2")],
    ])

    plan = await learn_pipeline.generate_card(issue, adapter)

    assert mock_ragas_eval.await_count == 3
    assert mock_build_card.await_count == 3
    mock_fallback_card.assert_awaited_once()
    assert plan.status == "completed"
    assert plan.llm_fallback is True
    assert plan.card_content["explanation"] == FALLBACK_CARD["explanation"]
    assert plan.card_content["before_code"] == issue.code_snippet


@pytest.mark.asyncio
async def test_ragas_passes_after_retry_stops_loop(mock_ragas_eval, mock_fallback_card, mock_build_card):
    """RAGAS 평가가 2번째 시도에 통과하면 즉시 루프를 멈추고 fallback은 호출하지 않는다 (T3)."""
    mock_ragas_eval.side_effect = [dict(FAILED_RESULT), dict(PASSED_RESULT)]
    issue = make_issue()
    adapter = FakeAdapter([
        [make_doc("security_guide doc 1"), make_doc("security_guide doc 2")],
        [make_doc("coding_convention doc 1"), make_doc("coding_convention doc 2")],
        [make_doc("learning_resource doc 1"), make_doc("learning_resource doc 2")],
    ])

    plan = await learn_pipeline.generate_card(issue, adapter)

    assert mock_ragas_eval.await_count == 2
    assert mock_build_card.await_count == 2
    mock_fallback_card.assert_not_awaited()
    assert plan.llm_fallback is False


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
