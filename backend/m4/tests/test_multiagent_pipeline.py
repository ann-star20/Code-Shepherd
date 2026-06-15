"""T15 — Phase 2 멀티에이전트 파이프라인 통합 테스트 (실제 모듈 간 연결 검증, Mock은 외부 API 경계까지만).

기존 test_pipeline.py/test_curator_agent.py/test_routes.py는 curator_agent/build_card/
embed_query/rag_search/ragas_eval/fallback_card를 모두 함수 단위로 mock하는 단위 테스트라
"여러 모듈이 실제로 맞물려 동작하는가"는 검증하지 않는다. 이 파일은 genai.GenerativeModel과
embed_query(Ollama HTTP)만 mock하고 나머지는 실제 코드 경로
(curator_agent → _embed_query_fields → rag_search → build_card → ragas_eval →
D26 재시도 → _run_card_generation)를 그대로 실행해, Bug A(Gemini 타임아웃)/Bug B(빈 embedding)
같은 통합 지점 버그를 잡아내는 회귀 테스트 안전망이다.

User journeys:
  As the Phase 2 learning pipeline, I want curator_agent → embed_query/rag_search →
  build_card → ragas_eval(D26 재시도 포함)이 실제로 연결되어 동작해서, 개발자별 맞춤
  학습 카드가 끝까지 생성되도록 하고 싶다.

  As the background task(_run_card_generation), 외부 LLM/임베딩 호출이 멈추거나 빈 값을
  반환해도 plan이 'running'에 영구히 멈추지 않고 'completed' 또는 'failed'로 끝나야 한다
  (Bug A/B가 실제로 발생한 지점).
"""

import asyncio
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.api import routes
from app.kms.search_adapter import PgvectorAdapter, SearchAdapter
from app.models.curriculum_plan import CurriculumPlan
from app.models.review_issue import ReviewIssue
from app.pipeline import curator_agent as curator_agent_module
from app.pipeline import learn_pipeline
from app.pipeline.learn_pipeline import generate_card


def make_issue(**overrides) -> ReviewIssue:
    defaults = dict(
        id=uuid.uuid4(),
        user_id=None,
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


def _docs(category: str) -> list[dict]:
    return [
        {"content": f"{category} 참고 문서 1", "metadata": {"category": category}},
        {"content": f"{category} 참고 문서 2", "metadata": {"category": category}},
    ]


DOCS_BY_CATEGORY = {
    "보안": _docs("보안"),
    "코딩컨벤션": _docs("코딩컨벤션"),
    "코드성능검증": _docs("코드성능검증"),
}

FIXED_CURATOR_INSTRUCTION = {
    "depth": "deep",
    "focus": "파라미터 바인딩 vs 문자열 포매팅의 차이",
    "analogy": "마스터키 틀에 맞춰 키를 깎는 비유",
    "key_points": ["사용자 입력은 절대 쿼리 문자열에 직접 삽입하지 않는다"],
    "card_type": "code_fix",
    "query_fields": {
        "보안": "SQL Injection 방지 가이드",
        "코딩컨벤션": "파라미터 바인딩 코딩 컨벤션",
        "코드성능검증": "SQL Injection 학습 자료 추천",
    },
}

# D26 narrow_query 재시도 시 curator_agent가 돌려줄 새 query_fields (FIXED와 길이가 달라야
# _fake_embed_query가 서로 다른 embedding을 생성해 재검색 여부를 구분할 수 있다)
RETRY_CURATOR_INSTRUCTION = {
    "depth": "deep",
    "focus": "더 좁은 초점 — 파라미터 바인딩 구현 세부사항",
    "analogy": "자물쇠에 맞는 열쇠를 매번 새로 깎는 비유",
    "key_points": ["prepared statement를 사용한다"],
    "card_type": "code_fix",
    "query_fields": {
        "보안": "SQL Injection 파라미터 바인딩 OWASP 가이드 상세",
        "코딩컨벤션": "Python SQLAlchemy 파라미터 바인딩 베스트 프랙티스 예시 모음",
        "코드성능검증": "SQL Injection 방지 테스트 코드 예시와 단위 테스트 모음",
    },
}

FIXED_CARD = {
    "explanation": "이 코드는 사용자 입력을 SQL 쿼리 문자열에 직접 삽입해 SQL Injection에 취약하다.",
    "why_dangerous": "공격자가 임의의 SQL을 실행해 DB 전체를 탈취하거나 변조할 수 있다.",
    "core_summary": "파라미터 바인딩을 사용해 사용자 입력과 쿼리를 분리하라.",
    "after_code": (
        "def search_products(keyword):\n"
        '    query = "SELECT * FROM products WHERE name LIKE %s"\n'
        "    return db.execute(query, (f'%{keyword}%',))"
    ),
    "learning_recommendations": [
        {"title": "SQL Injection 방지", "description": "파라미터 바인딩을 사용한다"},
    ],
}


def _is_curator_prompt(prompt: str) -> bool:
    """curator_agent의 프롬프트(CURATOR_PROMPT)에만 등장하는 "큐레이터"로 builder 프롬프트와 구분한다."""
    return "큐레이터" in prompt


def _make_fake_model(curator_instructions: list[dict], builder_cards: list[dict]):
    """genai.GenerativeModel 대체 — curator/builder 프롬프트를 구분해 순서대로 응답을 돌려준다.

    curator_agent_module.genai와 learn_pipeline.genai는 동일한 google.generativeai 모듈
    객체를 가리키므로, genai.GenerativeModel을 한 번만 monkeypatch하면 curator_agent()와
    build_card() 양쪽 호출에 모두 적용된다.
    """
    captured: list[str] = []
    calls = {"curator": 0, "builder": 0}

    class FakeGenerativeModel:
        def __init__(self, *_args, **_kwargs):
            pass

        async def generate_content_async(self, prompt, **_kwargs):
            captured.append(prompt)
            if _is_curator_prompt(prompt):
                idx = min(calls["curator"], len(curator_instructions) - 1)
                calls["curator"] += 1
                return SimpleNamespace(text=json.dumps(curator_instructions[idx]))
            idx = min(calls["builder"], len(builder_cards) - 1)
            calls["builder"] += 1
            return SimpleNamespace(text=json.dumps(builder_cards[idx]))

    return FakeGenerativeModel, captured


async def _fake_embed_query(text: str) -> list[float]:
    """Ollama bge-m3 embed_query 더블 — 빈 문자열에는 빈 리스트(Bug B 재현), 그 외에는
    텍스트 길이 기반으로 서로 구분 가능한 벡터를 돌려준다."""
    if not text:
        return []
    return [float(len(text))] * 4


class FakeAdapter(SearchAdapter):
    """SearchAdapter(D33) 더블 — DB 없이 category별 고정 문서를 돌려주고 호출(embedding, category)을 기록한다."""

    def __init__(self, docs_by_category: dict[str, list[dict]]):
        self._docs_by_category = docs_by_category
        self.calls: list[tuple[tuple[float, ...], str | None]] = []

    async def search(self, embedding, category=None, limit=3):
        self.calls.append((tuple(embedding), category))
        return list(self._docs_by_category.get(category, []))


# ---------------------------------------------------------------------------
# generate_card() — curator_agent ↔ embed_query/rag_search ↔ build_card 실제 연결
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_card_happy_path_wires_curator_search_and_builder(monkeypatch):
    """curator_agent → embed_query/rag_search(FakeAdapter) → build_card가 실제로 연결되어
    동작해 status='completed'인 CurriculumPlan을 만든다 (SKIP_RAGAS_EVAL로 평가 루프 생략)."""
    FakeModel, prompts = _make_fake_model(
        curator_instructions=[FIXED_CURATOR_INSTRUCTION],
        builder_cards=[FIXED_CARD],
    )
    monkeypatch.setattr(curator_agent_module.genai, "GenerativeModel", FakeModel)
    monkeypatch.setattr(learn_pipeline, "embed_query", _fake_embed_query)
    monkeypatch.setenv("SKIP_RAGAS_EVAL", "true")

    adapter = FakeAdapter(DOCS_BY_CATEGORY)
    issue = make_issue()

    plan = await generate_card(issue, adapter)

    assert plan.status == "completed"
    assert plan.llm_fallback is False
    assert plan.error_message is None
    assert plan.card_content["core_summary"] == FIXED_CARD["core_summary"]
    assert plan.card_content["before_code"] == issue.code_snippet
    assert plan.card_content["header"]["keyword"] == issue.keyword

    # curator_agent가 정한 query_fields(D22/T13)로 RAG 검색 3종이 실제로 호출됨
    assert {category for _, category in adapter.calls} == {"보안", "코딩컨벤션", "코드성능검증"}

    # build_card 프롬프트에 curator_instruction의 focus(T14/D23)가 실제로 전달됨
    builder_prompt = next(p for p in prompts if not _is_curator_prompt(p))
    assert FIXED_CURATOR_INSTRUCTION["focus"] in builder_prompt


@pytest.mark.asyncio
async def test_generate_card_d26_retry_recalls_curator_and_researches_with_new_query_fields(monkeypatch):
    """ragas_eval이 low_faithfulness로 실패하면 D26에 따라 curator_agent를 narrow_query hint로
    재호출하고, 새 query_fields로 embed_query/rag_search를 다시 수행한다 (T13/T14 실제 연결)."""
    FakeModel, prompts = _make_fake_model(
        curator_instructions=[FIXED_CURATOR_INSTRUCTION, RETRY_CURATOR_INSTRUCTION],
        builder_cards=[FIXED_CARD],
    )
    monkeypatch.setattr(curator_agent_module.genai, "GenerativeModel", FakeModel)
    monkeypatch.setattr(learn_pipeline, "embed_query", _fake_embed_query)

    ragas_results = iter(
        [
            {"passed": False, "reason": "low_faithfulness"},
            {"passed": True, "reason": None},
        ]
    )

    async def fake_ragas_eval(card, docs):
        return next(ragas_results)

    monkeypatch.setattr(learn_pipeline, "ragas_eval", fake_ragas_eval)

    adapter = FakeAdapter(DOCS_BY_CATEGORY)
    issue = make_issue()

    plan = await generate_card(issue, adapter)

    assert plan.status == "completed"
    assert plan.ragas_reason is None  # 두 번째 시도가 통과해 마지막 reason은 None

    curator_prompts = [p for p in prompts if _is_curator_prompt(p)]
    assert len(curator_prompts) == 2
    assert "검색 범위를 좁혀" not in curator_prompts[0]
    assert "검색 범위를 좁혀" in curator_prompts[1]

    # 카테고리 3개 × (최초 검색 + 재검색) = 6회, 재검색은 새 query_fields로 만든 새 embedding 사용
    assert len(adapter.calls) == 6
    categories_round1 = [category for _, category in adapter.calls[:3]]
    categories_round2 = [category for _, category in adapter.calls[3:]]
    assert categories_round1 == categories_round2 == ["보안", "코딩컨벤션", "코드성능검증"]
    embeddings_round1 = [embedding for embedding, _ in adapter.calls[:3]]
    embeddings_round2 = [embedding for embedding, _ in adapter.calls[3:]]
    assert embeddings_round1 != embeddings_round2


@pytest.mark.asyncio
async def test_generate_card_handles_empty_query_field_embedding_without_db_error(monkeypatch):
    """curator_instruction.query_fields의 한 카테고리가 빈 문자열이면 embed_query("")가
    embedding=[]을 돌려준다(Ollama 동작) — PgvectorAdapter.search()가 이 embedding=[]을
    받아도 asyncpg.exceptions.DataError 없이 빈 결과로 처리한다 (Bug B, 단위 테스트는
    test_search_adapter.py에서 별도 검증). "코드성능검증"이 비어 있으면 D37에 따라
    docs_recommend가 "보안" 카테고리에서 embedding1(비어 있지 않음)로 재검색되므로,
    embed_query("")의 빈 embedding은 adapter.search()에 전달되지 않는다.
    "코드성능검증"(docs_recommend)은 llm_fallback 판정과 무관하므로 generate_card는
    llm_fallback=False로 정상 완료된다."""
    curator_instruction_with_empty_field = {
        **FIXED_CURATOR_INSTRUCTION,
        "query_fields": {
            "보안": "SQL Injection 방지 가이드",
            "코딩컨벤션": "파라미터 바인딩 코딩 컨벤션",
            "코드성능검증": "",  # Curator가 빈 문자열을 반환하는 경우
        },
    }
    FakeModel, _ = _make_fake_model(
        curator_instructions=[curator_instruction_with_empty_field],
        builder_cards=[FIXED_CARD],
    )
    monkeypatch.setattr(curator_agent_module.genai, "GenerativeModel", FakeModel)
    monkeypatch.setattr(learn_pipeline, "embed_query", _fake_embed_query)
    monkeypatch.setenv("SKIP_RAGAS_EVAL", "true")

    session = AsyncMock()
    session.execute.return_value = SimpleNamespace(
        mappings=lambda: SimpleNamespace(all=lambda: [dict(doc, similarity=0.9) for doc in DOCS_BY_CATEGORY["보안"]])
    )
    adapter = PgvectorAdapter(session)
    issue = make_issue()

    plan = await generate_card(issue, adapter)

    assert plan.status == "completed"
    assert plan.llm_fallback is False  # 코드성능검증(docs_recommend)은 llm_fallback 판정과 무관
    # D37 — "코드성능검증"이 비어 있어 docs_recommend가 "보안"으로 재검색됨: 보안(concept) +
    # 코딩컨벤션(example) + 보안(recommend, 재검색) = 3회. 빈 embedding(코드성능검증)은 사용되지 않음
    assert session.execute.call_count == 3


# ---------------------------------------------------------------------------
# _run_card_generation() — 실제 generate_card 파이프라인 결과를 pending plan에 반영
# ---------------------------------------------------------------------------


class _FakeCardSession:
    """`_run_card_generation`이 사용하는 session_factory()의 async context manager 더블 (test_routes.py와 동일 패턴)."""

    def __init__(self, plans_by_id):
        self._plans = plans_by_id
        self.commit_count = 0

    async def get(self, _model, plan_id):
        return self._plans.get(plan_id)

    async def execute(self, _stmt):
        return SimpleNamespace(scalar_one=lambda: 0, all=lambda: [])

    async def commit(self):
        self.commit_count += 1

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeEngine:
    async def dispose(self):
        pass


def _patch_card_generation_infra(session, adapter):
    fake_settings = SimpleNamespace(database_url="postgresql://fake")
    return (
        patch("shared.config.get_settings", return_value=fake_settings),
        patch("shared.db.create_engine_from_url", return_value=_FakeEngine()),
        patch("shared.db.create_session_factory", return_value=lambda: session),
        patch.object(routes, "PgvectorAdapter", return_value=adapter),
    )


@pytest.mark.asyncio
async def test_run_card_generation_persists_real_generated_card_onto_plan(monkeypatch):
    """_run_card_generation이 실제 generate_card 파이프라인 결과를 pending plan에 정확히
    반영해 'completed' + card_content/header/llm_fallback/ragas_reason을 커밋한다."""
    FakeModel, _ = _make_fake_model(
        curator_instructions=[FIXED_CURATOR_INSTRUCTION],
        builder_cards=[FIXED_CARD],
    )
    monkeypatch.setattr(curator_agent_module.genai, "GenerativeModel", FakeModel)
    monkeypatch.setattr(learn_pipeline, "embed_query", _fake_embed_query)
    monkeypatch.setenv("SKIP_RAGAS_EVAL", "true")

    plan_id = uuid.uuid4()
    issue = make_issue()
    plan = CurriculumPlan(id=plan_id, issue_id=issue.id, status="pending", llm_fallback=False)
    session = _FakeCardSession({plan_id: plan})
    adapter = FakeAdapter(DOCS_BY_CATEGORY)

    p1, p2, p3, p4 = _patch_card_generation_infra(session, adapter)
    with p1, p2, p3, p4:
        await routes._run_card_generation([(plan_id, issue)])

    assert plan.status == "completed"
    assert plan.llm_fallback is False
    assert plan.error_message is None
    assert plan.card_content["core_summary"] == FIXED_CARD["core_summary"]
    assert plan.card_content["header"]["keyword"] == issue.keyword
    assert plan.ragas_reason is None


@pytest.mark.asyncio
async def test_run_card_generation_marks_plan_failed_when_curator_agent_times_out(monkeypatch):
    """curator_agent의 Gemini 호출이 응답 없이 멈추면 GEMINI_TIMEOUT_SECONDS 후 TimeoutError가
    발생하고, _generate_one의 예외 처리로 plan이 'running'에 영구히 멈추지 않고 'failed' +
    타임아웃 에러메시지로 기록된다 (Bug A, 재생성 중 실제로 발생한 버그)."""
    monkeypatch.setattr(curator_agent_module, "GEMINI_TIMEOUT_SECONDS", 0.05)

    class HangingGenerativeModel:
        def __init__(self, *_args, **_kwargs):
            pass

        async def generate_content_async(self, _prompt, **_kwargs):
            await asyncio.sleep(10)

    monkeypatch.setattr(curator_agent_module.genai, "GenerativeModel", HangingGenerativeModel)

    plan_id = uuid.uuid4()
    issue = make_issue()
    plan = CurriculumPlan(id=plan_id, issue_id=issue.id, status="pending", llm_fallback=False)
    session = _FakeCardSession({plan_id: plan})
    adapter = FakeAdapter(DOCS_BY_CATEGORY)

    p1, p2, p3, p4 = _patch_card_generation_infra(session, adapter)
    with p1, p2, p3, p4:
        await routes._run_card_generation([(plan_id, issue)])

    assert plan.status == "failed"
    assert "Gemini 응답 시간 초과" in plan.error_message
