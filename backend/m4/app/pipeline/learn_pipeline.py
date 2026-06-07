"""T2/T3 — 학습 카드 생성 파이프라인: 카드 타입 라우팅(D16) + RAG 검색(D15) + 카드 빌드 + RAGAS 평가 루프(Section 6)."""

import json
import os

import google.generativeai as genai
import httpx

from app.kms.search_adapter import (
    SearchAdapter,
    build_search1_text,
    build_search2_text,
    build_search3_text,
    embed_query,
    rag_search,
)
from app.models.curriculum_plan import CurriculumPlan
from app.models.review_issue import ReviewIssue

BUILDER_MODEL_NAME = "gemini-2.5-flash"
JUDGE_MODEL_NAME = "gemini-2.5-pro"
JUDGE_EMBEDDING_MODEL_NAME = "models/gemini-embedding-001"
RAGAS_PASS_THRESHOLD = 0.7


def route_card_type(issue: ReviewIssue) -> str:
    """D16 — code_snippet 존재 여부로 카드 타입(개념 설명 / 코드 수정)을 분기한다."""
    return "code_fix" if issue.code_snippet else "concept"


def determine_depth(issue: ReviewIssue, mistake_count: int = 0) -> str:
    """D18 — severity가 critical/high이거나 동일 keyword 실수가 7회 이상이면 deep, 아니면 quick."""
    return "deep" if (issue.severity in ("critical", "high") or mistake_count >= 7) else "quick"


def _format_docs(docs: list[dict] | None) -> str:
    if not docs:
        return "(검색된 참고 문서 없음 — 자체 지식 기반으로 작성)"
    return "\n".join(f"- {doc.get('content', '')}" for doc in docs)


async def build_card(
    *,
    issue: ReviewIssue,
    docs_concept: list[dict] | None,
    docs_example: list[dict] | None,
    docs_recommend: list[dict] | None,
    depth: str,
    card_type: str,
) -> dict:
    """Builder Agent (gemini-2.5-flash) — RAG 검색 결과 + 이슈 정보를 학습 카드 JSON으로 변환한다."""
    prompt = (
        "아래 코드 리뷰 이슈를 바탕으로 학습 카드를 JSON으로 생성해줘.\n"
        f"card_type: {card_type}\ndepth: {depth}\n"
        f"keyword: {issue.keyword}\nseverity: {issue.severity}\n"
        f"개념 설명 참고 자료(security_guide):\n{_format_docs(docs_concept)}\n"
        f"코딩 컨벤션 참고 자료(coding_convention):\n{_format_docs(docs_example)}\n"
        f"학습 추천 참고 자료(learning_resource):\n{_format_docs(docs_recommend)}\n"
        f"리뷰 대상 코드:\n{issue.code_snippet or '(code_snippet 없음)'}\n\n"
        "다음 키를 가진 JSON 객체만 반환해: "
        '{"explanation": string, "core_summary": string, "after_code": string|null, "recommendations": [string]}'
    )
    model = genai.GenerativeModel(BUILDER_MODEL_NAME)
    # response_mime_type 미지정 시 Gemini가 JSON을 마크다운 코드펜스(```json ... ```)로 감싸 반환해 json.loads가 실패함
    response = await model.generate_content_async(
        prompt,
        generation_config=genai.GenerationConfig(response_mime_type="application/json"),
    )
    return json.loads(response.text)


def _skip_ragas_eval() -> bool:
    """SKIP_RAGAS_EVAL=true — RAGAS 평가 루프를 건너뛰는 자체 cost-control 플래그 (spec 부록, BACKEND_SPEC.md 참조)."""
    return os.environ.get("SKIP_RAGAS_EVAL", "false").lower() == "true"


async def ragas_eval(card: dict, docs: list[dict]) -> dict:
    """Validator Agent (gemini-2.5-pro + RAGAS) — faithfulness/answer_relevancy ≥ 0.7 통과 여부를 판정한다 (Section 6).

    question=keyword 대신 카드의 핵심 주장(explanation+core_summary)을 answer로,
    검색된 문서 전체를 contexts로 사용해 "근거 문서에 충실한 카드인가"를 측정한다.
    reason은 Phase 1에서 항상 None — Phase 2(D14/T12)에서 전략 분기용으로 채워진다.
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
    sample = SingleTurnSample(
        user_input=card.get("explanation", ""),
        response=f"{card.get('explanation', '')}\n{card.get('core_summary', '')}",
        retrieved_contexts=[doc.get("content", "") for doc in docs],
    )
    faithfulness_score = await faithfulness.single_turn_ascore(sample)
    relevancy_score = await answer_relevancy.single_turn_ascore(sample)
    passed = faithfulness_score >= RAGAS_PASS_THRESHOLD and relevancy_score >= RAGAS_PASS_THRESHOLD
    return {"passed": passed, "reason": None}


async def fallback_card(*, issue: ReviewIssue, depth: str, card_type: str) -> dict:
    """RAGAS 평가 3회 실패 시 — RAG 컨텍스트 없이 LLM 자체 지식만으로 카드를 생성한다 (D30, "LLM 자체 생성" fallback)."""
    return await build_card(
        issue=issue,
        docs_concept=None,
        docs_example=None,
        docs_recommend=None,
        depth=depth,
        card_type=card_type,
    )


async def generate_card(issue: ReviewIssue, adapter: SearchAdapter) -> CurriculumPlan:
    """이슈 1건을 받아 RAG 검색 3종 → 카드 빌드 → curriculum_plan 레코드를 생성한다.

    embed_query 타임아웃 등 외부 API 오류는 status='failed' + error_message로 기록한다 (T6).
    """
    try:
        embedding1 = await embed_query(build_search1_text(issue))
        embedding2 = await embed_query(build_search2_text(issue))
        embedding3 = await embed_query(build_search3_text(issue))
    except httpx.TimeoutException as exc:
        return CurriculumPlan(
            issue_id=issue.id,
            status="failed",
            llm_fallback=False,
            error_message=f"embed_query timeout: {exc}",
            card_content=None,
        )

    docs_concept = await rag_search(adapter, embedding1, category="security_guide")
    docs_example = await rag_search(adapter, embedding2, category="coding_convention")
    docs_recommend = await rag_search(adapter, embedding3, category="learning_resource")

    llm_fallback = docs_concept is None or docs_example is None
    depth = determine_depth(issue)
    card_type = route_card_type(issue)

    if llm_fallback or _skip_ragas_eval():
        # llm_fallback=True면 docs가 없어 faithfulness 측정 대상이 없음(D30) → RAGAS 스킵
        # SKIP_RAGAS_EVAL=true면 비용 절감을 위해 평가 루프 자체를 건너뜀 (자체 cost-control 플래그)
        card_content = await build_card(
            issue=issue,
            docs_concept=docs_concept,
            docs_example=docs_example,
            docs_recommend=docs_recommend,
            depth=depth,
            card_type=card_type,
        )
    else:
        # docs 3개 합산해서 RAGAS contexts로 전달 (Section 6)
        all_docs = [*(docs_concept or []), *(docs_example or []), *(docs_recommend or [])]
        for _attempt in range(3):
            card_content = await build_card(
                issue=issue,
                docs_concept=docs_concept,
                docs_example=docs_example,
                docs_recommend=docs_recommend,
                depth=depth,
                card_type=card_type,
            )
            result = await ragas_eval(card_content, all_docs)
            if result["passed"]:
                break
        else:
            # 3회 모두 실패 → fallback_card()로 대체, llm_fallback=True (T3)
            card_content = await fallback_card(issue=issue, depth=depth, card_type=card_type)
            llm_fallback = True

    # before_code: code_snippet 없으면 null (프론트에서 단일 컬럼 렌더링)
    card_content["before_code"] = issue.code_snippet or None

    return CurriculumPlan(
        issue_id=issue.id,
        status="completed",
        llm_fallback=llm_fallback,
        error_message=None,
        card_content=card_content,
    )
