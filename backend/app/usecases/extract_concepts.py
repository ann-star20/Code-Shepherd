"""G4: extract_concepts — 청크별 LLM 호출 + 중복 제거."""

from pydantic import ValidationError

from app.domain.models import ConceptExtractionSchema
from app.infrastructure.llm.interface import ILLMClient


async def extract_concepts(
    doc_id: str,
    chunks: list[str],
    llm: ILLMClient,
) -> list[ConceptExtractionSchema]:
    seen: set[str] = set()
    results: list[ConceptExtractionSchema] = []

    for chunk in chunks:
        try:
            concepts = await llm.extract_concepts(chunk, doc_id, {})
            for concept in concepts:
                if concept.concept_name not in seen:
                    seen.add(concept.concept_name)
                    results.append(concept)
        except (ValidationError, Exception):
            continue

    return results
