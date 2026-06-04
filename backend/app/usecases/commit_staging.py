"""G9: commit_staging — APPROVED → concepts + Neo4j → COMMITTED."""

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
            """SELECT id, doc_id, concept_name, concept_domain, severity,
                      description_ko, concept_type, cwe_id, owasp_id,
                      aliases, security_mechanisms, affected_components,
                      config_properties, root_cause
               FROM staging_concepts
               WHERE session_id = $1::uuid AND status = 'APPROVED'
               FOR UPDATE SKIP LOCKED""",
            session_id,
        )

        if not rows:
            return 0

        count = 0
        for row in rows:
            def _loads(v) -> list:
                if isinstance(v, str):
                    return json.loads(v)
                return list(v or [])

            concept = ConceptExtractionSchema(
                concept_name=row["concept_name"],
                concept_domain=row["concept_domain"],
                severity=row["severity"].upper(),
                description_ko=row["description_ko"],
                concept_type=row["concept_type"],
                cwe_id=row["cwe_id"],
                owasp_id=row["owasp_id"],
                aliases=_loads(row["aliases"]),
                security_mechanisms=_loads(row["security_mechanisms"]),
                affected_components=_loads(row["affected_components"]),
                config_properties=_loads(row["config_properties"]),
                root_cause=row["root_cause"],
            )

            await conn.execute(
                """INSERT INTO concepts
                   (concept_name, concept_domain, severity, description_ko,
                    concept_type, cwe_id, owasp_id,
                    aliases, security_mechanisms, affected_components,
                    config_properties, root_cause,
                    first_seen_doc_id, last_updated_doc_id)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9::jsonb,$10::jsonb,$11::jsonb,$12,$13,$13)
                   ON CONFLICT (concept_name, concept_domain) DO UPDATE
                   SET severity             = EXCLUDED.severity,
                       description_ko       = EXCLUDED.description_ko,
                       last_updated_doc_id  = EXCLUDED.last_updated_doc_id,
                       updated_at           = NOW()""",
                concept.concept_name,
                concept.concept_domain.value,
                concept.severity.lower(),
                concept.description_ko,
                concept.concept_type,
                concept.cwe_id,
                getattr(concept, "owasp_id", None),
                json.dumps(concept.aliases),
                json.dumps(concept.security_mechanisms),
                json.dumps(concept.affected_components),
                json.dumps(concept.config_properties),
                concept.root_cause,
                row["doc_id"],
            )

            await write_concept_node(concept, driver)

            await conn.execute(
                """UPDATE staging_concepts
                   SET status = 'COMMITTED', updated_at = NOW()
                   WHERE id = $1""",
                row["id"],
            )
            count += 1

    return count
