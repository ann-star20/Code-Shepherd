"""PostgreSQL 스키마 적용 및 초기 Concept 시드 적재 v2.

PRD-schema.md §15.2 DDL 적용 후,
security_concepts.json + perf_concepts.json의 Concept 데이터를
concepts 테이블에 UPSERT (ON CONFLICT DO UPDATE).

Usage:
    python backend/scripts/seed_postgres.py
"""

import json
import os
import sys
from pathlib import Path

import psycopg2

SEED_DIR = Path(__file__).parent / "seed"
SEC_DIR  = SEED_DIR / "security"
PERF_DIR = SEED_DIR / "performance"

SCHEMA_FILE = SEC_DIR / "schema.sql"

_UPSERT_CONCEPT = """
INSERT INTO concepts (
    concept_name, domains, concept_type,
    cwe_id, owasp_id, severity, description_ko, aliases
) VALUES (
    %(concept_name)s, %(domains)s, %(concept_type)s,
    %(cwe_id)s, %(owasp_id)s, %(severity)s, %(description_ko)s, %(aliases)s
)
ON CONFLICT (concept_name) DO UPDATE SET
    domains        = EXCLUDED.domains,
    concept_type   = EXCLUDED.concept_type,
    cwe_id         = EXCLUDED.cwe_id,
    owasp_id       = EXCLUDED.owasp_id,
    severity       = EXCLUDED.severity,
    description_ko = EXCLUDED.description_ko,
    aliases        = EXCLUDED.aliases,
    updated_at     = now()
"""


def _concept_row(c: dict) -> dict:
    return {
        "concept_name": c["name"],
        "domains":      c.get("domains", []),
        "concept_type": c.get("concept_type", None),
        "cwe_id":       c.get("cwe_id", None),
        "owasp_id":     c.get("owasp_id", None),
        "severity":     c.get("severity", None),
        "description_ko": c.get("description_ko", None),
        "aliases":      c.get("aliases", []),
    }


def main():
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5433")),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "postgres"),
        dbname=os.getenv("DB_NAME", "postgres"),
    )
    try:
        with conn.cursor() as cur:
            # 1. DDL 적용
            print("[1/2] PostgreSQL DDL v2 applying...")
            cur.execute(SCHEMA_FILE.read_text(encoding="utf-8"))

            # 2. Concept 시드 적재
            sec_concepts  = json.loads((SEC_DIR  / "security_concepts.json").read_text("utf-8"))["concepts"]
            perf_concepts = json.loads((PERF_DIR / "perf_concepts.json").read_text("utf-8"))["concepts"]
            all_concepts  = sec_concepts + perf_concepts

            print(f"[2/2] Seeding {len(all_concepts)} concepts...")
            for c in all_concepts:
                cur.execute(_UPSERT_CONCEPT, _concept_row(c))

        conn.commit()

        with conn.cursor() as cur:
            cur.execute("SELECT unnest(domains) AS domain, COUNT(*) FROM concepts GROUP BY domain ORDER BY domain")
            rows = cur.fetchall()

        print("seed OK:")
        for domain, cnt in rows:
            print(f"   {domain}: {cnt}건")

    except Exception as e:
        conn.rollback()
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
