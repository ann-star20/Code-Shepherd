"""T2/T3 — 학습 카드 생성 파이프라인: 카드 타입 라우팅(D16) + RAG 검색(D15) + 카드 빌드 + RAGAS 평가 루프(Section 6)."""

import asyncio
import json
import os
import re

import google.generativeai as genai
import httpx
from langsmith import traceable
from langsmith.run_helpers import tracing_context

from app.kms.search_adapter import (
    SearchAdapter,
    build_search1_text,
    embed_query,
    rag_search,
)
from app.models.curriculum_plan import CurriculumPlan
from app.models.review_issue import ReviewIssue
from app.pipeline.curator_agent import GEMINI_TIMEOUT_SECONDS, DeveloperProfile, curator_agent

BUILDER_MODEL_NAME = "gemini-2.5-flash"
JUDGE_MODEL_NAME = "gemini-2.5-pro"
JUDGE_EMBEDDING_MODEL_NAME = "models/gemini-embedding-001"
RAGAS_PASS_THRESHOLD = 0.7

_CARD_PROMPT_BODY = (
    "card_type: {card_type}\ndepth: {depth}\n"
    "keyword: {keyword}\nseverity: {severity}\nsub_category: {sub_category}\n"
    "{curator_guidance}"
    "개념 설명 참고 자료(security_guide):\n{docs_concept}\n"
    "코딩 컨벤션 참고 자료(coding_convention):\n{docs_example}\n"
    "학습 추천 참고 자료(learning_resource):\n{docs_recommend}\n"
    "코드 맥락(code_context): {code_context}\n"
    "리뷰 대상 코드:\n{code_snippet}\n\n"
    "다음 키를 가진 JSON 객체만 반환해 (마크다운 문법 사용 금지 — **bold**, # 헤더, bullet 기호 등 절대 쓰지 말 것):\n"
    "- explanation: 이 취약점이 무엇인지, e-commerce 서비스 맥락에서 왜 위험한지를 포함해 최대 한 단락으로 설명 (개발자가 쉽게 이해할 수 있게)\n"
    "- why_dangerous: e-commerce 환경에서 이 취약점이 실제로 어떤 피해를 줄 수 있는지 최대 한 단락으로 구체적으로 설명\n"
    "- core_summary: 핵심 한 줄 요약 (마크다운 없이 평문)\n"
    "- after_code: 위의 '리뷰 대상 코드'를 keyword와 sub_category 기준의 이슈를 직접 수정한 코드. 새로운 예시 코드 작성 금지. 코드펜스 기호 없이 순수 코드만. 핵심 변경사항에는 해당 코드 바로 윗줄에 별도 줄로 코멘트 추가 (인라인 코멘트 금지)\n"
    "- learning_recommendations: 학습 추천 최대 7개, 각각 title(짧은 제목)과 description(한 문장). "
    "리뷰 대상 코드의 구체적인 문제(예: 어떤 메서드/패턴을 썼는지)와 연결해서 추천해줘\n"
    '{{"explanation": string, "why_dangerous": string, "core_summary": string, "after_code": string|null, "learning_recommendations": [{{"title": string, "description": string}}]}}'
)

# D18 — depth별로 Builder Agent에게 다른 깊이의 카드를 지시하는 템플릿 (T10)
DEEP_CARD_PROMPT = (
    "아래 코드 리뷰 이슈를 바탕으로 학습 카드를 JSON으로 생성해줘.\n"
    "이 카드는 심화 학습용이다 — severity가 높거나 같은 실수를 반복한 개발자를 위한 것이다. "
    "정보량을 늘리는 게 아니라 '이번엔 확실히 이해되게' 만드는 게 목표이므로, "
    "기초 개념부터 차근차근 설명하고 비유와 구체적인 예시를 풍부하게 사용해줘.\n"
    + _CARD_PROMPT_BODY
)
QUICK_CARD_PROMPT = (
    "아래 코드 리뷰 이슈를 바탕으로 학습 카드를 JSON으로 생성해줘.\n"
    "이 카드는 빠른 확인용이다 — 핵심만 간결하게 요약해서 짧은 시간 안에 확인할 수 있도록 작성해줘.\n"
    + _CARD_PROMPT_BODY
)


def route_card_type(issue: ReviewIssue) -> str:
    """D16 — code_snippet 존재 여부로 카드 타입(개념 설명 / 코드 수정)을 분기한다."""
    return "code_fix" if issue.code_snippet else "concept"


def determine_depth(issue: ReviewIssue, mistake_count: int = 0) -> str:
    """D18 — severity가 critical/high이거나 동일 keyword 실수가 3회 이상이면 deep, 아니면 quick."""
    return "deep" if (issue.severity in ("critical", "high") or mistake_count >= 3) else "quick"


def _parse_llm_json(text: str) -> dict:
    """Gemini 응답을 JSON으로 파싱 — 마크다운 코드펜스 제거 후 시도."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?\s*```$", "", text)
        text = text.strip()
    return json.loads(text)


def _format_docs(docs: list[dict] | None) -> str:
    if not docs:
        return "(검색된 참고 문서 없음 — 자체 지식 기반으로 작성)"
    lines = []
    for doc in docs:
        lines.append(f"- {doc.get('content', '')}")
        parent_content = doc.get("parent_content")
        if parent_content:
            lines.append(f"  (관련 맥락: {parent_content})")
    return "\n".join(lines)


def _format_curator_guidance(curator_instruction: dict | None) -> str:
    """curator_instruction(D22)의 focus/analogy/key_points를 Builder 프롬프트에 추가 지시로 전달한다 (T14/D23, additive)."""
    if curator_instruction is None:
        return ""
    key_points = curator_instruction.get("key_points") or []
    return (
        "Curator 지시 — 이 개발자에게 맞춰 아래 초점/비유/핵심 포인트를 카드에 반영해줘:\n"
        f"focus: {curator_instruction.get('focus', '')}\n"
        f"analogy: {curator_instruction.get('analogy', '')}\n"
        f"key_points: {', '.join(key_points)}\n"
    )


@traceable(run_type="llm", name="build_card")
async def build_card(
    *,
    issue: ReviewIssue,
    docs_concept: list[dict] | None,
    docs_example: list[dict] | None,
    docs_recommend: list[dict] | None,
    depth: str,
    card_type: str,
    curator_instruction: dict | None = None,
) -> dict:
    """Builder Agent (gemini-2.5-flash) — RAG 검색 결과 + 이슈 정보를 학습 카드 JSON으로 변환한다.

    curator_instruction(D22)을 넘기면 focus/analogy/key_points를 프롬프트에 추가 지시로 포함한다 (T14/D23, additive).
    """
    template = DEEP_CARD_PROMPT if depth == "deep" else QUICK_CARD_PROMPT
    prompt = template.format(
        card_type=card_type,
        depth=depth,
        keyword=issue.keyword,
        severity=issue.severity,
        sub_category=issue.sub_category or "(없음)",
        curator_guidance=_format_curator_guidance(curator_instruction),
        docs_concept=_format_docs(docs_concept),
        docs_example=_format_docs(docs_example),
        docs_recommend=_format_docs(docs_recommend),
        code_context=issue.code_context or "(없음)",
        code_snippet=issue.code_snippet or "(code_snippet 없음)",
    )
    model = genai.GenerativeModel(BUILDER_MODEL_NAME)
    # response_mime_type 미지정 시 Gemini가 JSON을 마크다운 코드펜스(```json ... ```)로 감싸 반환해 json.loads가 실패함
    # Gemini가 가끔 malformed JSON을 반환하므로 최대 3회 재시도
    last_exc: Exception = RuntimeError("build_card: no attempts made")
    for _ in range(3):
        try:
            response = await asyncio.wait_for(
                model.generate_content_async(
                    prompt,
                    generation_config=genai.GenerationConfig(response_mime_type="application/json"),
                ),
                timeout=GEMINI_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:
            raise TimeoutError(f"build_card: Gemini 응답 시간 초과 ({GEMINI_TIMEOUT_SECONDS}s)") from exc
        try:
            return _parse_llm_json(response.text)
        except json.JSONDecodeError as e:
            last_exc = e
    raise last_exc


def _skip_ragas_eval() -> bool:
    """SKIP_RAGAS_EVAL=true — RAGAS 평가 루프를 건너뛰는 자체 cost-control 플래그 (spec 부록, BACKEND_SPEC.md 참조)."""
    return os.environ.get("SKIP_RAGAS_EVAL", "false").lower() == "true"


def _ragas_reason(faithfulness_score: float, relevancy_score: float) -> str | None:
    """평가 실패 원인을 D26 재시도 힌트(curator_agent._retry_hint) 분기용으로 분류한다 (T12/D14).

    faithfulness 미달이 relevancy 미달보다 우선한다 — 문서에 근거하지 않은 카드는
    "질문과 관련 있는가"를 따지기 전에 먼저 근거 자체를 narrow_query로 좁혀야 하기 때문.
    """
    if faithfulness_score < RAGAS_PASS_THRESHOLD:
        return "low_faithfulness"
    if relevancy_score < RAGAS_PASS_THRESHOLD:
        return "low_relevancy"
    return None


# D26 — ragas_reason → curator_agent hint 매핑 (T13). 매핑에 없는 reason(None 등)은 hint=None으로 처리.
_RETRY_HINT_BY_REASON = {
    "low_faithfulness": "narrow_query",
    "low_relevancy": "change_framing",
}


@traceable(run_type="chain", name="ragas_eval")
async def ragas_eval(card: dict, docs: list[dict]) -> dict:
    """Validator Agent (gemini-2.5-pro + RAGAS) — faithfulness/answer_relevancy ≥ 0.7 통과 여부를 판정한다 (Section 6).

    question=keyword 대신 카드의 핵심 주장(explanation+core_summary)을 answer로,
    검색된 문서 전체를 contexts로 사용해 "근거 문서에 충실한 카드인가"를 측정한다.
    reason은 통과 시 None, 실패 시 "low_faithfulness"|"low_relevancy" (T12/D14, _ragas_reason 참조).
    """
    from ragas import SingleTurnSample
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import answer_relevancy, faithfulness
    from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

    judge_llm = LangchainLLMWrapper(ChatGoogleGenerativeAI(model=JUDGE_MODEL_NAME))
    faithfulness.llm = judge_llm
    answer_relevancy.llm = judge_llm
    # answer_relevancy는 생성된 질문과 원 질문의 코사인 유사도를 계산하므로 judge LLM과 별개로 임베딩 모델이 필요함.
    # ragas 네이티브 GoogleEmbeddings는 embed_text만 제공해 구버전 인터페이스(embed_query)를 쓰는 answer_relevancy와 호환되지 않음
    answer_relevancy.embeddings = LangchainEmbeddingsWrapper(
        GoogleGenerativeAIEmbeddings(model=JUDGE_EMBEDDING_MODEL_NAME)
    )
    retrieved_contexts: list[str] = []
    for doc in docs:
        retrieved_contexts.append(doc.get("content", ""))
        parent_content = doc.get("parent_content")
        if parent_content:
            retrieved_contexts.append(parent_content)

    sample = SingleTurnSample(
        user_input=card.get("explanation", ""),
        response=f"{card.get('explanation', '')}\n{card.get('core_summary', '')}",
        retrieved_contexts=retrieved_contexts,
    )
    try:
        faithfulness_score, relevancy_score = await asyncio.wait_for(
            asyncio.gather(
                faithfulness.single_turn_ascore(sample),
                answer_relevancy.single_turn_ascore(sample),
            ),
            timeout=GEMINI_TIMEOUT_SECONDS,
        )
    except TimeoutError as exc:
        raise TimeoutError(f"ragas_eval: RAGAS judge LLM 응답 시간 초과 ({GEMINI_TIMEOUT_SECONDS}s)") from exc
    passed = faithfulness_score >= RAGAS_PASS_THRESHOLD and relevancy_score >= RAGAS_PASS_THRESHOLD
    return {"passed": passed, "reason": _ragas_reason(faithfulness_score, relevancy_score)}


async def fallback_card(
    *,
    issue: ReviewIssue,
    depth: str,
    card_type: str,
    curator_instruction: dict | None = None,
) -> dict:
    """RAGAS 평가 3회 실패 시 — RAG 컨텍스트 없이 LLM 자체 지식만으로 카드를 생성한다 (D30, "LLM 자체 생성" fallback)."""
    return await build_card(
        issue=issue,
        docs_concept=None,
        docs_example=None,
        docs_recommend=None,
        depth=depth,
        card_type=card_type,
        curator_instruction=curator_instruction,
    )


@traceable(run_type="retriever", name="embed_query_fields")
async def _embed_query_fields(query_fields: dict[str, str]) -> tuple[list[float], list[float], list[float]]:
    """query_fields(보안/코딩컨벤션/코드성능검증) 3개를 동시에 임베딩한다 — 지연시간을 합산이 아닌 최대값으로 줄인다."""
    return await asyncio.gather(
        embed_query(query_fields["보안"]),
        embed_query(query_fields["코딩컨벤션"]),
        embed_query(query_fields["코드성능검증"]),
    )


def _concept_search_params(
    issue: ReviewIssue,
    query_fields: dict[str, str],
    embedding1: list[float],
    embedding3: list[float],
) -> tuple[list[float], str]:
    """D37 — query_fields["보안"]이 D15 fallback(build_search1_text)과 동일하면 Gemini가 이
    이슈를 보안과 무관하다고 판단해 비워뒀다는 뜻이므로, "개념 설명" 참고자료(docs_concept)는
    "코드성능검증" 카테고리에서 검색한다."""
    if query_fields["보안"] == build_search1_text(issue):
        return embedding3, "코드성능검증"
    return embedding1, "보안"


def _recommend_search_params(
    query_fields: dict[str, str],
    embedding1: list[float],
    embedding3: list[float],
) -> tuple[list[float], str]:
    """D37 — query_fields["코드성능검증"]이 비어 있으면(fallback 없음) Gemini가 이 이슈를
    성능과 무관하다고 판단했다는 뜻이므로, "학습 추천" 참고자료(docs_recommend)는 "보안"
    카테고리에서 검색한다."""
    if not query_fields["코드성능검증"]:
        return embedding1, "보안"
    return embedding3, "코드성능검증"


@traceable(name="generate_card")
async def generate_card(
    issue: ReviewIssue,
    adapter: SearchAdapter,
    mistake_count: int = 0,
    profile: DeveloperProfile | None = None,
    config: dict | None = None,
) -> CurriculumPlan:
    """이슈 1건을 받아 RAG 검색 3종 → 카드 빌드 → curriculum_plan 레코드를 생성한다.

    config["metadata"]["trace_id"](AgentHarness.run()이 주입)를 tracing_context로 전파해,
    내부에서 호출되는 curator_agent/rag_search/build_card/ragas_eval의 LangSmith run이
    모두 같은 trace_id로 묶여 "카드 생성 전체 과정"을 한 그룹으로 볼 수 있게 한다.
    """
    meta = (config or {}).get("metadata") or {}
    with tracing_context(metadata=meta):
        return await _generate_card_impl(issue, adapter, mistake_count, profile)


async def _generate_card_impl(
    issue: ReviewIssue,
    adapter: SearchAdapter,
    mistake_count: int = 0,
    profile: DeveloperProfile | None = None,
) -> CurriculumPlan:
    """이슈 1건을 받아 RAG 검색 3종 → 카드 빌드 → curriculum_plan 레코드를 생성한다.

    RAG 검색어는 D15의 고정 규칙(build_search1/2/3_text) 대신 Curator Agent가 정한
    curator_instruction.query_fields(보안/코딩컨벤션/코드성능검증)를 사용한다 (T13/D22).
    embed_query 타임아웃 등 외부 API 오류는 status='failed' + error_message로 기록한다 (T6).
    """
    if profile is None:
        profile = {"weak_categories": [], "past_mistakes": []}

    curator_instruction = await curator_agent(profile=profile, issue=issue)
    query_fields = curator_instruction["query_fields"]

    try:
        embedding1, embedding2, embedding3 = await _embed_query_fields(query_fields)
    except httpx.TimeoutException as exc:
        return CurriculumPlan(
            issue_id=issue.id,
            status="failed",
            llm_fallback=False,
            error_message=f"embed_query timeout: {exc}",
            card_content=None,
            curator_instruction=curator_instruction,
            attempt_count=0,
        )

    concept_embedding, concept_category = _concept_search_params(issue, query_fields, embedding1, embedding3)
    recommend_embedding, recommend_category = _recommend_search_params(query_fields, embedding1, embedding3)
    docs_concept = await rag_search(adapter, concept_embedding, category=concept_category)
    docs_example = await rag_search(adapter, embedding2, category="코딩컨벤션")
    docs_recommend = await rag_search(adapter, recommend_embedding, category=recommend_category)

    llm_fallback = docs_concept is None or docs_example is None
    depth = determine_depth(issue, mistake_count=mistake_count)
    card_type = route_card_type(issue)

    ragas_reason: str | None = None
    attempt_count = 0
    try:
        if llm_fallback or _skip_ragas_eval():
            # llm_fallback=True면 docs가 없어 faithfulness 측정 대상이 없음(D30) → RAGAS 스킵
            # SKIP_RAGAS_EVAL=true면 비용 절감을 위해 평가 루프 자체를 건너뜀 (자체 cost-control 플래그)
            attempt_count = 1
            card_content = await build_card(
                issue=issue,
                docs_concept=docs_concept,
                docs_example=docs_example,
                docs_recommend=docs_recommend,
                depth=depth,
                card_type=card_type,
                curator_instruction=curator_instruction,
            )
        else:
            # docs 3개 합산해서 RAGAS contexts로 전달 (Section 6)
            all_docs = [*(docs_concept or []), *(docs_example or []), *(docs_recommend or [])]
            for attempt in range(3):
                attempt_count = attempt + 1
                card_content = await build_card(
                    issue=issue,
                    docs_concept=docs_concept,
                    docs_example=docs_example,
                    docs_recommend=docs_recommend,
                    depth=depth,
                    card_type=card_type,
                    curator_instruction=curator_instruction,
                )
                try:
                    result = await ragas_eval(card_content, all_docs)
                except TimeoutError:
                    # RAGAS judge LLM 응답 시간 초과 — 재시도해도 같은 judge 호출을 다시 기다려야 해
                    # 타임아웃이 반복될 가능성이 높으므로, low_faithfulness/low_relevancy처럼 재시도하지
                    # 않고 즉시 루프를 멈춘다. card_content는 이미 RAG 문서로 build_card()가 만들어 둔
                    # 결과이므로(llm_fallback=False 유지) RAGAS 검증만 건너뛰고 그대로 사용한다 —
                    # fallback_card()(RAG 없음)로 대체하면 learning_recommendations의 RAG 기반
                    # 일관성이 깨진다.
                    ragas_reason = "ragas_timeout"
                    break
                ragas_reason = result["reason"]
                if result["passed"]:
                    break
                if attempt < 2:
                    # D26 — 실패 원인(ragas_reason)에 맞는 hint로 curator_agent를 재호출해
                    # query_fields를 다시 정하고 RAG를 재검색한다.
                    hint = _RETRY_HINT_BY_REASON.get(ragas_reason)
                    curator_instruction = await curator_agent(profile=profile, issue=issue, hint=hint)
                    query_fields = curator_instruction["query_fields"]
                    embedding1, embedding2, embedding3 = await _embed_query_fields(query_fields)
                    concept_embedding, concept_category = _concept_search_params(issue, query_fields, embedding1, embedding3)
                    recommend_embedding, recommend_category = _recommend_search_params(query_fields, embedding1, embedding3)
                    docs_concept = await rag_search(adapter, concept_embedding, category=concept_category)
                    docs_example = await rag_search(adapter, embedding2, category="코딩컨벤션")
                    docs_recommend = await rag_search(adapter, recommend_embedding, category=recommend_category)
                    all_docs = [*(docs_concept or []), *(docs_example or []), *(docs_recommend or [])]
            else:
                # 3회 모두 실패 → fallback_card()로 대체, llm_fallback=True (T3)
                card_content = await fallback_card(
                    issue=issue,
                    depth=depth,
                    card_type=card_type,
                    curator_instruction=curator_instruction,
                )
                llm_fallback = True
    except Exception as exc:
        # build_card()/fallback_card() — Gemini API 오류, JSON 파싱 실패 등 (T6).
        # fallback_card()는 RAGAS 3회 실패 후의 마지막 안전망이라 여기서도 실패하면 더 이상 대안이 없음 → status='failed'로 기록
        return CurriculumPlan(
            issue_id=issue.id,
            status="failed",
            llm_fallback=False,
            error_message=str(exc),
            card_content=None,
            curator_instruction=curator_instruction,
            attempt_count=attempt_count,
        )

    # before_code: code_snippet 없으면 null (프론트에서 단일 컬럼 렌더링)
    card_content["before_code"] = issue.code_snippet or None
    # after_code에 마크다운 코드펜스가 포함된 경우 제거
    if card_content.get("after_code"):
        card_content["after_code"] = re.sub(r"^```[\w]*\n?", "", card_content["after_code"]).rstrip("`").strip()
    # header: issue 메타데이터에서 직접 구성 (LLM 생성 불필요)
    card_content["header"] = {
        "keyword": issue.keyword,
        "name_of_function": issue.name_of_function or "",
        "language": issue.programming_language or "",
        "framework": issue.framework or "",
        "framework_version": issue.framework_version or "",
    }

    return CurriculumPlan(
        issue_id=issue.id,
        status="completed",
        llm_fallback=llm_fallback,
        error_message=None,
        card_content=card_content,
        ragas_reason=ragas_reason,
        curator_instruction=curator_instruction,
        attempt_count=attempt_count,
    )
