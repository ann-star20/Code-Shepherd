"""PostgreSQL 시드 스크립트 — 완전 멱등성 UPSERT 기반 초기화.

APP_MODE=development 시 MockEmbeddingService로 name_vector / desc_vector를 자동 충전한다.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.infrastructure.llm.mock_embedding import MockEmbeddingService  # noqa: E402

_APP_MODE = os.getenv("APP_MODE", "development")
_embedder = MockEmbeddingService() if _APP_MODE != "production" else None


def _vec_str(vec: list[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in vec) + "]"

# ── 경로 상수 명세화
SCRIPTS_DIR    = Path(__file__).parent
SCHEMA_SQL     = SCRIPTS_DIR / "seed" / "schema.sql"
SEC_JSON       = SCRIPTS_DIR / "seed" / "security" / "security_concepts.json"
PERF_JSON      = SCRIPTS_DIR / "seed" / "performance" / "performance_concepts.json"


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
    print(f"  [Schema] {SCHEMA_SQL.name} 통합본 원자적 적용 완료")


async def _upsert_concepts(conn: asyncpg.Connection, concepts: list[dict]) -> int:
    inserted = 0
    for c in concepts:
        severity = c.get("severity")
        if severity == "info":
            severity = "low"
        owasp = c.get("owasp_id") or c.get("owasp_category")

        name_vec_str: str | None = None
        desc_vec_str: str | None = None
        if _embedder is not None:
            aliases: list[str] = c.get("aliases", [])
            name_corpus = " ".join([c["concept_name"]] + aliases)
            name_vec_str = _vec_str(_embedder.embed(name_corpus))
            desc_ko = c.get("description_ko", "")
            desc_vec_str = _vec_str(_embedder.embed(desc_ko)) if desc_ko else None

        await conn.execute(
            """
            INSERT INTO concepts
                (concept_name, domains, concept_type, cwe_id, owasp_id,
                 severity, description_ko, root_cause, aliases,
                 name_vector, desc_vector)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9,
                    $10::vector, $11::vector)
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
                root_cause     = EXCLUDED.root_cause,
                name_vector    = COALESCE(EXCLUDED.name_vector, concepts.name_vector),
                desc_vector    = COALESCE(EXCLUDED.desc_vector, concepts.desc_vector),
                updated_at     = now()
            """,
            c["concept_name"],
            c.get("domains", ["security"]),
            c.get("concept_type", "vulnerability_root_cause"),
            c.get("cwe_id"),
            owasp,
            severity,
            c.get("description_ko", ""),
            c.get("root_cause", ""),
            c.get("aliases", []),
            name_vec_str,
            desc_vec_str,
        )
        inserted += 1
    return inserted


async def main() -> None:
    dsn = _dsn()
    print(f"[seed_postgres] 엔티티 클린 통합 시드 기동: {dsn.split('@')[-1]}")

    conn = await asyncpg.connect(dsn)
    try:
        print("[1/3] 통합 스키마 DDL 레이어 빌드...")
        await _apply_schema(conn)

        print("[2/3] 보안 도메인 수렴 개념 마스터 시드 적재 (Aliases 확장 탑재)...")
        sec_data: list[dict] = json.loads(SEC_JSON.read_text(encoding="utf-8"))
        n_sec = await _upsert_concepts(conn, sec_data)
        print(f"  → {n_sec}건")

        print("[3/3] 성능 도메인 안티패턴 개념 마스터 시드 적재...")
        perf_data: list[dict] = json.loads(PERF_JSON.read_text(encoding="utf-8"))
        n_perf = await _upsert_concepts(conn, perf_data)
        print(f"  → {n_perf}건")

        print(f"\n[완료] 총 {n_sec + n_perf}건 통합 적재 수렴 — 구조 무결성 보장")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())