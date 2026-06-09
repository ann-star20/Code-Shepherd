"""APP_MODE 기반 LLM/Embedding 클라이언트 팩토리. PRD §16.6."""

from __future__ import annotations
from app.infrastructure.llm.interface import ILLMClient


def create_llm_client(app_mode: str = "development", **kwargs) -> ILLMClient:
    """APP_MODE에 따라 MockClient 또는 GeminiClient를 반환한다.

    Args:
        app_mode: "production" → GeminiClient, 그 외 → MockClient
        **kwargs: GeminiClient 초기화 파라미터 (api_key, langsmith_project)
    """
    if app_mode == "production":
        from app.infrastructure.llm.gemini_client import GeminiClient

        return GeminiClient(
            api_key=kwargs["api_key"],
            model=kwargs.get("model", "gemini-2.5-flash"),
            langsmith_project=kwargs.get("langsmith_project", ""),
        )
    from app.infrastructure.llm.mock_client import MockClient

    return MockClient()


def create_embedding_client(mode: str = "development", **kwargs):
    """임베딩 모드에 따라 MockEmbeddingService 또는 GeminiEmbeddingService를 반환한다.

    Args:
        mode: "production" → GeminiEmbeddingService, 그 외 → MockEmbeddingService
        **kwargs: GeminiEmbeddingService 초기화 파라미터 (api_key, model)
    """
    if mode == "production":
        from app.infrastructure.llm.gemini_embedding import GeminiEmbeddingService

        return GeminiEmbeddingService(
            api_key=kwargs["api_key"],
            model=kwargs.get("model", "text-embedding-004"),
        )
    from app.infrastructure.llm.mock_embedding import MockEmbeddingService

    return MockEmbeddingService()
