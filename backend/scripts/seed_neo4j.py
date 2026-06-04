"""Neo4j OWASP 2025 Tag Node 시드 스크립트.

Usage: python backend/scripts/seed_neo4j.py
"""

import json
import os
import sys
from pathlib import Path
from neo4j import GraphDatabase

SEED_FILE = Path(__file__).parent / "seed" / "security" / "owasp_2025.json"

_MERGE_OWASP = """
MERGE (t:Tag {name: $owasp_id})
  ON CREATE SET t.label    = $name,
                t.label_ko = $name_ko,
                t.severity = $severity,
                t.type     = 'owasp'
RETURN t.name AS tag
"""

_MERGE_CWE = """
MERGE (t:Tag {name: $cwe_id})
  ON CREATE SET t.type = 'cwe'
RETURN t.name AS tag
"""


def main():
    uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    pw = os.getenv("NEO4J_PASSWORD", "pass1234!")

    data = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    driver = GraphDatabase.driver(uri, auth=(user, pw))

    try:
        with driver.session() as session:
            for cat in data["categories"]:
                session.run(
                    _MERGE_OWASP,
                    owasp_id=cat["owasp_id"],
                    name=cat["name"],
                    name_ko=cat["name_ko"],
                    severity=cat["severity"],
                )
                for cwe in cat.get("cwe_ids", []):
                    session.run(_MERGE_CWE, cwe_id=cwe)
            count = session.run("MATCH (t:Tag) RETURN count(t) AS n").single()["n"]
        print(f"seed OK: {count} Tag nodes total")
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
