"""GeminiEmbeddingService — text-embedding-004 모델을 사용한 실제 임베딩 서비스."""

from __future__ import annotations
import logging

logger = logging.getLogger(__name__)


class GeminiEmbeddingService:
    """Gemini text-embedding-004 API를 호출하여 768차원 임베딩 벡터를 반환한다."""

    def __init__(self, api_key: str, model: str = "text-embedding-004") -> None:
        """Gemini 임베딩 클라이언트 초기화.

        Args:
            api_key: Google Gemini API 키
            model: 임베딩 모델명 (기본값: "text-embedding-004")
        """
        try:
            from google import genai

            self._client = genai.Client(api_key=api_key)
            self._model_name = model
            logger.info("GeminiEmbeddingService 초기화 — model: %s", model)
        except ImportError as exc:
            raise RuntimeError(
                "google-genai 패키지가 없습니다: pip install google-genai"
            ) from exc

    async def embed_text(self, text: str) -> list[float]:
        """단일 텍스트를 임베딩한다.

        Args:
            text: 임베딩할 텍스트

        Returns:
            768차원 임베딩 벡터 (list[float])
        """
        try:
            response = self._client.models.embed_content(
                model=self._model_name,
                content=text,
            )
            embedding = response.embedding
            if not isinstance(embedding, list):
                embedding = list(embedding)
            return embedding
        except Exception as exc:
            logger.error("Gemini 임베딩 API 호출 실패: %s", exc)
            raise

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """텍스트 배치를 임베딩한다.

        Args:
            texts: 임베딩할 텍스트 목록

        Returns:
            임베딩 벡터 목록 (각 벡터는 768차원)
        """
        embeddings = []
        for text in texts:
            embedding = await self.embed_text(text)
            embeddings.append(embedding)
        return embeddings
