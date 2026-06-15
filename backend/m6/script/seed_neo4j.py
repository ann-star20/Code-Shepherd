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
.\.venv-win\Scripts\python.exe script\seed_neo4j.py    
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
# SCRIPTS_DIR = Path(__file__).parent
# SEC_JSON = SCRIPTS_DIR / "concept.json"

def _driver() -> neo4j.AsyncDriver:
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7688")
    user = os.getenv("NEO4J_USER", "neo4j")
    pw = os.getenv("NEO4J_PASSWORD", "codeshepherd")
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
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7688")
    print(f"[seed_neo4j] 연결: {uri}")

    driver = _driver()
    try:
        # docker compose 최초 기동 시 neo4j 컨테이너가 아직 준비되지 않았을 수 있으므로 재시도
        for attempt in range(1, 31):
            try:
                await driver.verify_connectivity()
                break
            except Exception as exc:
                print(f"[seed_neo4j] Neo4j 연결 대기 중... ({attempt}/30) {exc}")
                await asyncio.sleep(2)
        else:
            raise RuntimeError("Neo4j 연결 실패 - 30회 재시도 초과")

        repo = Neo4jConceptRepo(driver)

        # 1. 스키마 초기화 — 8대 제약조건 + 인덱스
        print("[1/3] Neo4j 스키마 초기화...")
        await repo.init_schema(CYPHER_PATH)
        print("  → 제약조건·인덱스 적용 완료")
        
        print("[추가] L1 도메인 거점 노드(security, performance) 생성 중...")
        async with driver.session() as session:
            await session.execute_write(
                lambda tx: tx.run("MERGE (:Domain {name: 'security'})")
            )
            await session.execute_write(
                lambda tx: tx.run("MERGE (:Domain {name: 'performance'})")
            )
        print("  → 도메인 거점 구축 완료")
        
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

        print("[대기] 데이터베이스 커밋 동기화 중 (0.5초)...")
        await asyncio.sleep(0.5)
        
        # ── ⭕ 변경 2: 명시적 쓰기 트랜잭션으로 뼈대선과 교차점 완벽 종결 ──
        print("[추가] L1 도메인 - L2 개념 간의 BELONGS_TO 교차점 및 뼈대선 자동 완공 중...")
        async with driver.session() as session:
            query = """
                MATCH (c:Concept), (d:Domain)
                WHERE d.name IN c.domains
                MERGE (c)-[:BELONGS_TO]->(d)
            """
            await session.execute_write(lambda tx: tx.run(query))
            
        print("   → 4-레이어 온톨로지 종속성 및 교차점 연결 완전 성공!")

        print(f"\n[완료] 총 {n_sec + n_perf}건 — 멱등성 보장 (중복 실행 안전)")
    finally:
        await driver.close()


if __name__ == "__main__":
    asyncio.run(main())
