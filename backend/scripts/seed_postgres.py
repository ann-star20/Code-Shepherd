"""PostgreSQL 시드 스크립트 — 완전 멱등성 UPSERT 기반 초기화.

실행:
    cd backend
    python scripts/seed_postgres.py

환경변수 (우선순위: DATABASE_URL > 개별 변수):
    DATABASE_URL   postgresql://user:pass@host:port/dbname
    DB_HOST        localhost
    DB_PORT        5433
    DB_NAME        postgres
    DB_USER        postgres
    DB_PASSWORD    postgres
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── 경로 상수 ─────────────────────────────────────────────────────────────────

SCRIPTS_DIR = Path(__file__).parent
SCHEMA_SQL  = SCRIPTS_DIR / "seed" / "security" / "schema.sql"
SEC_JSON    = SCRIPTS_DIR / "seed" / "security" / "security_concepts.json"
PERF_JSON   = SCRIPTS_DIR / "seed" / "performance" / "performance_concepts.json"


def _dsn() -> str:
    if url := os.getenv("DATABASE_URL"):
        return url
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5433")
    name = os.getenv("DB_NAME", "postgres")
    user = os.getenv("DB_USER", "postgres")
    pw   = os.getenv("DB_PASSWORD", "postgres")
    return f"postgresql://{user}:{pw}@{host}:{port}/{name}"


async def _apply_schema(conn: asyncpg.Connection) -> None:
    sql = SCHEMA_SQL.read_text(encoding="utf-8")
    statements = [s.strip() for s in sql.split(";") if s.strip()]
    for stmt in statements:
        lines = [ln for ln in stmt.splitlines() if not ln.strip().startswith("--")]
        body = "\n".join(lines).strip()
        if body:
            await conn.execute(body)
    print(f"  [schema] {SCHEMA_SQL.name} 적용 완료")


async def _upsert_concepts(conn: asyncpg.Connection, concepts: list[dict]) -> int:
    inserted = 0
    for c in concepts:
        severity = c.get("severity")
        if severity == "info":
            severity = "low"
        owasp = c.get("owasp_id") or c.get("owasp_category")
        await conn.execute(
            """
            INSERT INTO concepts
                (concept_name, domains, concept_type, cwe_id, owasp_id,
                 severity, description_ko, aliases)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (concept_name) DO UPDATE
            SET
                domains        = (SELECT array(
                                    SELECT DISTINCT unnest(concepts.domains || EXCLUDED.domains)
                                  )),
                aliases        = (SELECT array(
                                    SELECT DISTINCT unnest(concepts.aliases || EXCLUDED.aliases)
                                  )),
                severity       = EXCLUDED.severity,
                description_ko = EXCLUDED.description_ko,
                updated_at     = now()
            """,
            c["concept_name"],
            c.get("domains", ["security"]),
            c.get("concept_type", "vulnerability_root_cause"),
            c.get("cwe_id"),
            owasp,
            severity,
            c.get("description_ko", ""),
            c.get("aliases", []),
        )
        inserted += 1
    return inserted


async def main() -> None:
    dsn = _dsn()
    print(f"[seed_postgres] 연결: {dsn.split('@')[-1]}")

    conn = await asyncpg.connect(dsn)
    try:
        print("[1/3] 스키마 DDL 적용...")
        await _apply_schema(conn)

        print("[2/3] 보안 도메인 개념 UPSERT...")
        sec_data: list[dict] = json.loads(SEC_JSON.read_text(encoding="utf-8"))
        n_sec = await _upsert_concepts(conn, sec_data)
        print(f"  → {n_sec}건")

        print("[3/3] 성능 도메인 개념 UPSERT...")
        perf_data: list[dict] = json.loads(PERF_JSON.read_text(encoding="utf-8"))
        n_perf = await _upsert_concepts(conn, perf_data)
        print(f"  → {n_perf}건")

        print(f"\n[완료] 총 {n_sec + n_perf}건 — 멱등성 보장")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
