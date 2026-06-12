"""APP_MODE 기반 LLM/Embedding 클라이언트 팩토리. PRD §16.6."""

from __future__ import annotations
import os
from app.infrastructure.llm.interface import ILLMClient
import logging

logger = logging.getLogger(__name__)

# ── Embedding 싱글톤 (ForkPoolWorker 프로세스당 1회 로드) ────────────────────
# worker_process_init 시그널(celery_app.py)이 시작 시 warm_up → 이후 호출은 즉시 반환
_embedding_instance = None


def create_llm_client(app_mode: str = "development", **kwargs) -> ILLMClient:
    """APP_MODE에 따라 MockClient 또는 GeminiClient를 반환한다."""
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
    """mock / production 공통으로 BgeEmbeddingClient(BAAI/bge-m3)를 반환한다.

    mode 인수는 하위 호환을 위해 유지하지만 분기에 사용하지 않는다.
    싱글톤으로 관리하므로 프로세스당 모델 로드는 1회만 발생한다.

    # 구형 MockEmbeddingService(BoW) / GeminiEmbeddingService(text-embedding-004) 폐기.
    # 두 파일은 mock_embedding.py / gemini_embedding.py에 보존.
    """
    global _embedding_instance
    if _embedding_instance is not None:
        return _embedding_instance

    model_name = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
    from app.infrastructure.llm.bge_client import BgeEmbeddingClient

    _embedding_instance = BgeEmbeddingClient(model_name)
    return _embedding_instance
