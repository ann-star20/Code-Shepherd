"""G9+G13: commit_staging — APPROVED → concepts + Neo4j → COMMITTED.

규칙④: concepts 커밋 성공 시 동일 트랜잭션에서 documents.state='COMMITTED' 동기화.
"""

import json

import asyncpg
import neo4j

from app.domain.models import ConceptExtractionSchema
from app.infrastructure.graph.graph_writer import write_concept_node


async def commit_staging(
    session_id: str,
    conn: asyncpg.Connection,
    driver: neo4j.AsyncDriver,
) -> int:
    async with conn.transaction():
        rows = await conn.fetch(
            """SELECT id, doc_id, concept_json
               FROM staging_concepts
               WHERE session_id = $1::uuid AND state = 'APPROVED'
               FOR UPDATE SKIP LOCKED""",
            session_id,
        )

        if not rows:
            return 0

        committed_doc_ids: set[str] = set()
        count = 0

        for row in rows:
            raw = row["concept_json"]
            data = json.loads(raw) if isinstance(raw, str) else dict(raw)
            concept = ConceptExtractionSchema(**data)

            # concepts.severity CHECK: lowercase (critical/high/medium/low)
            sev = (concept.severity if concept.severity != "INFO" else "LOW").lower()

            await conn.execute(
                """INSERT INTO concepts
                   (concept_name, doc_id, domains, severity, description_ko,
                    concept_type, cwe_id, owasp_id, aliases)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                   ON CONFLICT (concept_name) DO UPDATE
                   SET domains        = (SELECT array(
                                           SELECT DISTINCT unnest(concepts.domains || EXCLUDED.domains)
                                         )),
                       severity       = EXCLUDED.severity,
                       description_ko = EXCLUDED.description_ko,
                       updated_at     = NOW()""",
                concept.concept_name,
                row["doc_id"],
                concept.domains,
                sev,
                concept.description_ko,
                concept.concept_type,
                concept.cwe_id,
                concept.owasp_id,
                concept.aliases,
            )

            await write_concept_node(concept, driver)

            await conn.execute(
                "UPDATE staging_concepts SET state='COMMITTED', committed_at=NOW() WHERE id=$1",
                row["id"],
            )

            if row["doc_id"]:
                committed_doc_ids.add(row["doc_id"])
            count += 1

        # 규칙④: 출처 document 상태를 COMMITTED로 동기화 (동일 트랜잭션)
        if committed_doc_ids:
            await conn.execute(
                "UPDATE documents SET state='COMMITTED', updated_at=NOW() "
                "WHERE doc_id = ANY($1)",
                list(committed_doc_ids),
            )

    return count
