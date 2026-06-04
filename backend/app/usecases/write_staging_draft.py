"""G5: write_staging_draft — staging_concepts DRAFT 행 삽입."""

import json

import asyncpg

from app.domain.models import ConceptExtractionSchema


async def write_staging_draft(
    session_id: str,
    doc_id: str,
    concepts: list[ConceptExtractionSchema],
    conn: asyncpg.Connection,
) -> int:
    count = 0
    for concept in concepts:
        await conn.execute(
            """INSERT INTO staging_concepts
               (session_id, doc_id, concept_name, concept_domain, severity,
                description_ko, concept_type, cwe_id, owasp_id,
                aliases, security_mechanisms, affected_components,
                config_properties, root_cause)
               VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9,
                       $10::jsonb, $11::jsonb, $12::jsonb, $13::jsonb, $14)""",
            session_id,
            doc_id,
            concept.concept_name,
            concept.concept_domain.value,          # enum → 소문자 문자열
            concept.severity.lower(),              # "HIGH" → "high" (DB CHECK 소문자)
            concept.description_ko,
            concept.concept_type,
            concept.cwe_id,
            getattr(concept, "owasp_id", None),
            json.dumps(concept.aliases),
            json.dumps(concept.security_mechanisms),
            json.dumps(concept.affected_components),
            json.dumps(concept.config_properties),
            concept.root_cause,
        )
        count += 1
    return count
