"""RAGAS 품질 평가 — context_precision + faithfulness.

USE_MOCK_LLM=true 시 자동 스킵.
LLM: claude-haiku-4-5-20251001 (langchain-anthropic) 우선, OpenAI gpt-4o-mini 폴백.
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

_RAGAS_LLM_MODEL = "claude-haiku-4-5-20251001"
_OPENAI_FALLBACK = "gpt-4o-mini"


def _patch_vertexai_compat() -> None:
    """langchain-community 0.4.x 에서 제거된 chat_models.vertexai 경로를 shim으로 채운다.

    ragas 0.4.x 는 아직 구 경로를 임포트하므로 모듈 레벨에서 패치한다.
    """
    import sys
    import types
    if "langchain_community.chat_models.vertexai" not in sys.modules:
        stub = types.ModuleType("langchain_community.chat_models.vertexai")
        try:
            from langchain_google_vertexai import ChatVertexAI
            stub.ChatVertexAI = ChatVertexAI
        except ImportError:
            stub.ChatVertexAI = type("ChatVertexAI", (), {})  # 빈 더미
        sys.modules["langchain_community.chat_models.vertexai"] = stub
        # 상위 패키지에도 등록
        parent = sys.modules.get("langchain_community.chat_models")
        if parent is not None:
            parent.vertexai = stub


def evaluate_ragas(question: str, answer: str, contexts: list[str]) -> dict[str, float]:
    """RAGAS context_precision + faithfulness 평가. 오류 / mock 모드 시 빈 dict 반환."""
    if os.getenv("USE_MOCK_LLM", "false").lower() == "true":
        return {}
    if not question or not answer or not contexts:
        return {}
    try:
        _patch_vertexai_compat()
        from ragas import evaluate
        from ragas.dataset_schema import EvaluationDataset, SingleTurnSample
        from ragas.llms import LangchainLLMWrapper
        from ragas.metrics import Faithfulness, LLMContextPrecisionWithoutReference

        # Anthropic Haiku 우선, OpenAI 폴백
        try:
            from langchain_anthropic import ChatAnthropic
            llm = LangchainLLMWrapper(ChatAnthropic(model=_RAGAS_LLM_MODEL, temperature=0))
        except ImportError:
            from langchain_openai import ChatOpenAI
            llm = LangchainLLMWrapper(ChatOpenAI(model=_OPENAI_FALLBACK, temperature=0))

        metrics = [
            LLMContextPrecisionWithoutReference(llm=llm),
            Faithfulness(llm=llm),
        ]

        sample = SingleTurnSample(
            user_input=question,
            response=answer,
            retrieved_contexts=contexts,
        )
        dataset = EvaluationDataset(samples=[sample])
        result = evaluate(dataset, metrics=metrics)

        scores: dict[str, float] = {}
        raw: dict = result.scores[0] if result.scores else {}
        for key, val in raw.items():
            k = str(key).lower()
            if "precision" in k:
                scores["context_precision"] = float(val)
            elif "faithfulness" in k:
                scores["faithfulness"] = float(val)
        return scores
    except Exception as exc:
        log.warning("ragas eval skipped: %s", exc)
        return {}
