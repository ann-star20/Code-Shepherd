"""write_staging_draft — staging_concepts DRAFT / DOMAIN_PENDING 행 삽입 (PRD §3.9.2 v2).

스키마 v2: concept_json JSONB (개별 컬럼 아님).
domain 분류: registered_domains와 교차 → known/unknown 분리 → state 결정.
"""

import json

import asyncpg

from app.domain.models import ConceptExtractionSchema


async def write_staging_draft(
    session_id: str,
    doc_id: str,
    concepts: list[ConceptExtractionSchema],
    conn: asyncpg.Connection,
    registered_domains: set[str] | None = None,
) -> int:
    """staging_concepts에 DRAFT 또는 DOMAIN_PENDING 행 삽입.

    Args:
        registered_domains: None이면 분류 없이 모두 DRAFT.
    Returns:
        삽입된 행 수.
    """
    count = 0
    for concept in concepts:
        concept_json = json.dumps(concept.model_dump())

        if registered_domains is not None:
            known = [d for d in concept.domains if d in registered_domains]
            unknown = [d for d in concept.domains if d not in registered_domains]
        else:
            known, unknown = list(concept.domains), []

        state = "DOMAIN_PENDING" if unknown else "DRAFT"

        await conn.execute(
            """INSERT INTO staging_concepts
               (session_id, doc_id, concept_json, state, known_domains, unknown_domains)
               VALUES ($1::uuid, $2, $3::jsonb, $4, $5, $6)""",
            session_id,
            doc_id,
            concept_json,
            state,
            known,
            unknown,
        )
        count += 1
    return count
