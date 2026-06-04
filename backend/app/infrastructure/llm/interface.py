"""ILLMClient — LLM 추출 클라이언트 추상 인터페이스 (DIP 계약). PRD §16.3."""
from abc import ABC, abstractmethod
from app.domain.models import ConceptExtractionSchema


class ILLMClient(ABC):
    @abstractmethod
    async def extract_concepts(
        self,
        text_chunk: str,
        doc_id: str,
        metadata: dict,
    ) -> list[ConceptExtractionSchema]:
        """공식 문서 청크에서 구조화 컨셉 목록을 추출한다."""

    @abstractmethod
    def is_tracing_enabled(self) -> bool:
        """LangSmith 트레이싱 활성화 여부."""
