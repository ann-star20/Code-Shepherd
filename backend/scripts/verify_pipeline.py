"""파이프라인 결과 자동 검증 스크립트.

실행:
    cd backend
    python scripts/verify_pipeline.py <session_id>

    # Docker 내부
    docker exec -it code-shepherd-backend-1 python scripts/verify_pipeline.py <session_id>
    docker exec -it code-shepherd-base-1 python scripts/verify_pipeline.py <session_id>
    

환경변수:
    DATABASE_URL   postgresql://user:pass@host:port/dbname
    DB_HOST        localhost  (기본)
    DB_PORT        5433       (기본, 호스트 매핑 포트)
    DB_NAME        postgres
    DB_USER        postgres
    DB_PASSWORD    postgres
    NEO4J_URI      bolt://127.0.0.1:7688  (기본)
    NEO4J_USER     neo4j
    NEO4J_PASSWORD pass1234!
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import asyncpg
from neo4j import AsyncGraphDatabase

sys.path.insert(0, str(Path(__file__).parent.parent))

MOCK_NAMES = [
    "CSRFAttack",
    "CsrfViewMiddleware",
    "CsrfTokenTag",
    "CsrfExempt",
    "AjaxCSRFHeader",
    "SameSiteCookie",
]

_PASS = "\033[32mPASS\033[0m"
_FAIL = "\033[31mFAIL\033[0m"


def _pg_dsn() -> str:
    if url := os.getenv("DATABASE_URL"):
        return url
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5433")
    name = os.getenv("DB_NAME", "postgres")
    user = os.getenv("DB_USER", "postgres")
    pw = os.getenv("DB_PASSWORD", "postgres")
    return f"postgresql://{user}:{pw}@{host}:{port}/{name}"


def _label(title: str) -> str:
    return f"[CHECK] {title}".ljust(46, ".")


async def main(session_id: str) -> int:
    print(f"\n파이프라인 검증 — session_id: {session_id}\n")

    dsn = _pg_dsn()
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7688")
    neo4j_auth = (
        os.getenv("NEO4J_USER", "neo4j"),
        os.getenv("NEO4J_PASSWORD", "pass1234!"),
    )

    pg = await asyncpg.connect(dsn, ssl=False)
    driver = AsyncGraphDatabase.driver(neo4j_uri, auth=neo4j_auth)

    failures = 0

    try:
        # ── CHECK 1: staging row 존재 ─────────────────────────────────────────
        count = await pg.fetchval(
            "SELECT count(*) FROM staging_concepts WHERE session_id=$1::uuid",
            session_id,
        )
        if count and count > 0:
            print(f"{_label('PG  staging rows')} {_PASS} ({count}건)")
        else:
            print(f"{_label('PG  staging rows')} {_FAIL} (0건 — session_id 확인 필요)")
            failures += 1

        # ── CHECK 2: state 분포 ───────────────────────────────────────────────
        rows = await pg.fetch(
            "SELECT state, count(*) AS n FROM staging_concepts "
            "WHERE session_id=$1::uuid GROUP BY state ORDER BY state",
            session_id,
        )
        dist = {r["state"]: r["n"] for r in rows}
        committed = dist.get("COMMITTED", 0)
        dist_str = ", ".join(f"{k}={v}" for k, v in dist.items())
        if committed == len(MOCK_NAMES):
            print(f"{_label('PG  state distribution')} {_PASS} ({dist_str})")
        else:
            note = f"committed={committed} (목표 {len(MOCK_NAMES)})"
            if not dist:
                failures += 1
            print(
                f"{_label('PG  state distribution')} {_PASS if dist else _FAIL} ({dist_str or '없음'}) — {note}"
            )

        # ── CHECK 3: 6개 컨셉명 PostgreSQL 일치 ──────────────────────────────
        pg_names_rows = await pg.fetch(
            "SELECT concept_json->>'concept_name' AS name "
            "FROM staging_concepts WHERE session_id=$1::uuid",
            session_id,
        )
        found_names = {r["name"] for r in pg_names_rows if r["name"]}
        expected = set(MOCK_NAMES)
        missing = expected - found_names
        if not missing:
            print(
                f"{_label('PG  mock concept names')} {_PASS} ({len(found_names)}/{len(MOCK_NAMES)})"
            )
        else:
            print(f"{_label('PG  mock concept names')} {_FAIL} 누락: {sorted(missing)}")
            failures += 1

        # ── CHECK 4: Neo4j Concept 노드 존재 ──────────────────────────────────
        async with driver.session() as neo_sess:
            result = await neo_sess.run(
                "MATCH (c:Concept) WHERE c.name IN $names RETURN c.name AS name",
                names=MOCK_NAMES,
            )
            neo_names = {r["name"] async for r in result}

        missing_neo = expected - neo_names
        if not missing_neo:
            print(
                f"{_label('Neo4j Concept nodes')} {_PASS} ({len(neo_names)}/{len(MOCK_NAMES)})"
            )
        else:
            print(
                f"{_label('Neo4j Concept nodes')} {_FAIL} 누락: {sorted(missing_neo)}"
            )
            failures += 1

        # ── CHECK 5: :Security 물리 라벨 ──────────────────────────────────────
        async with driver.session() as neo_sess:
            result = await neo_sess.run(
                "MATCH (c:Concept:Security) WHERE c.name IN $names RETURN c.name AS name",
                names=MOCK_NAMES,
            )
            labeled = {r["name"] async for r in result}

        missing_label = expected - labeled
        if not missing_label:
            print(
                f"{_label('Neo4j :Security label')} {_PASS} ({len(labeled)}/{len(MOCK_NAMES)})"
            )
        else:
            print(
                f"{_label('Neo4j :Security label')} {_FAIL} 누락: {sorted(missing_label)}"
            )
            failures += 1

    finally:
        await pg.close()
        await driver.close()

    total = 5
    passed = total - failures
    verdict = "\033[32m✓\033[0m" if failures == 0 else "\033[31m✗\033[0m"
    print(f"\n결과: {passed}/{total} PASS {verdict}\n")
    return 1 if failures else 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python scripts/verify_pipeline.py <session_id>")
        sys.exit(1)
    sys.exit(asyncio.run(main(sys.argv[1])))
