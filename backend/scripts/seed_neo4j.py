"""Neo4j 시드 스크립트 — 완전 멱등성 MERGE 기반 초기화.

실행:
    cd backend
    python scripts/seed_neo4j.py

환경변수:
    NEO4J_URI       bolt://localhost:7688
    NEO4J_USER      neo4j
    NEO4J_PASSWORD  password

의존:
    Neo4j APOC 플러그인 (apoc.create.addLabels, apoc.coll.toSet)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import neo4j

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.adapters.db.neo4j_repo import Neo4jConceptRepo
from app.domain.models import ConceptExtractionSchema

# ── 경로 상수 ─────────────────────────────────────────────────────────────────

SCRIPTS_DIR = Path(__file__).parent
CYPHER_PATH = SCRIPTS_DIR / "init_db.cypher"
SEC_JSON = SCRIPTS_DIR / "seed" / "security" / "security_concepts.json"
PERF_JSON = SCRIPTS_DIR / "seed" / "performance" / "performance_concepts.json"


def _driver() -> neo4j.AsyncDriver:
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7688")
    user = os.getenv("NEO4J_USER", "neo4j")
    pw = os.getenv("NEO4J_PASSWORD", "password")
    return neo4j.AsyncGraphDatabase.driver(uri, auth=(user, pw))


async def _seed_batch(
    repo: Neo4jConceptRepo,
    data: list[dict],
    domain_label: str,
) -> int:
    merged = 0
    for raw in data:
        try:
            concept = ConceptExtractionSchema(**raw)
            master = await repo.merge_concept(concept)
            print(f"  [OK] {domain_label} → '{master}'")
            merged += 1
        except Exception as exc:
            name = raw.get("concept_name", "?")
            print(f"  [ERR] {domain_label}/{name}: {exc}")
    return merged


async def main() -> None:
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    print(f"[seed_neo4j] 연결: {uri}")

    driver = _driver()
    try:
        await driver.verify_connectivity()
        repo = Neo4jConceptRepo(driver)

        # 1. 스키마 초기화 — 8대 제약조건 + 인덱스
        print("[1/3] Neo4j 스키마 초기화...")
        await repo.init_schema(CYPHER_PATH)
        print("  → 제약조건·인덱스 적용 완료")

        # 2. 보안 도메인 시드
        print("[2/3] 보안 도메인 Concept MERGE...")
        sec_data: list[dict] = json.loads(SEC_JSON.read_text(encoding="utf-8"))
        n_sec = await _seed_batch(repo, sec_data, "security")
        print(f"  → {n_sec}건")

        # 3. 성능 도메인 시드
        print("[3/3] 성능 도메인 Concept MERGE...")
        perf_data: list[dict] = json.loads(PERF_JSON.read_text(encoding="utf-8"))
        n_perf = await _seed_batch(repo, perf_data, "performance")
        print(f"  → {n_perf}건")

        print(f"\n[완료] 총 {n_sec + n_perf}건 — 멱등성 보장 (중복 실행 안전)")
    finally:
        await driver.close()


if __name__ == "__main__":
    asyncio.run(main())
