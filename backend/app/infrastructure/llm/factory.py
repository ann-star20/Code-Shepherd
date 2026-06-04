"""APP_MODE 기반 LLM 클라이언트 팩토리. PRD §16.6."""
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
            langsmith_project=kwargs.get("langsmith_project", ""),
        )
    from app.infrastructure.llm.mock_client import MockClient
    return MockClient()
