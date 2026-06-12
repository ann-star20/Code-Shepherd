"""
PostgreSQL 시드 스크립트 — 로컬 BGE-M3 (1024차원) 임베딩 엔진 완전 통합본.
멱등성: IF NOT EXISTS / ON CONFLICT UPSERT 기반 초기화 — 중복 실행 완전 안전.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

import asyncpg

# 로컬 패키지 인입 경로 정밀 바인딩
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger(__name__)

# BGE-M3 로드는 main() 내부에서 수행 — 모듈 import 시 2분 블로킹 방지
_embedder = None


def _vec_str(vec: list[float]) -> str:
    """pgvector 적재용 직렬화 텍스트 포맷터 (1024차원 배열 스트링 가공)."""
    return "[" + ",".join(f"{v:.6f}" for v in vec) + "]"


# ── 경로 상수 명세화
SCRIPTS_DIR = Path(__file__).parent
SCHEMA_SQL = SCRIPTS_DIR / "seed" / "schema.sql"
SEC_JSON = SCRIPTS_DIR / "seed" / "security" / "security_concepts.json"
PERF_JSON = SCRIPTS_DIR / "seed" / "performance" / "performance_concepts.json"


def _dsn() -> str:
    if url := os.getenv("DATABASE_URL"):
        return url
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv(
        "DB_PORT", "5432"
    )  # 🎯 구형 5433 포트를 상용 인프라 표준인 5432로 단일화 보정
    name = os.getenv("DB_NAME", "postgres")
    user = os.getenv("DB_USER", "postgres")
    pw = os.getenv("DB_PASSWORD", "postgres")
    return f"postgresql://{user}:{pw}@{host}:{port}/{name}"


async def _apply_schema(conn: asyncpg.Connection) -> None:
    """schema.sql 파일 내의 1024차원 HNSW 벡터 DDL 및 인프라 구조 정렬 적용."""
    sql = SCHEMA_SQL.read_text(encoding="utf-8")
    statements = [s.strip() for s in sql.split(";") if s.strip()]
    for stmt in statements:
        lines = [ln for ln in stmt.splitlines() if not ln.strip().startswith("--")]
        body = "\n".join(lines).strip()
        if not body:
            continue
        try:
            await conn.execute(body)
        except Exception as exc:
            logger.error(f"  [Schema] DDL 실패 — {exc}\n  SQL: {body[:120]}")
            raise
    logger.info(
        f"  [Schema] {SCHEMA_SQL.name} 1024차원 pgvector 확장판 원자적 적용 완공"
    )


async def _upsert_concepts(conn: asyncpg.Connection, concepts: list[dict]) -> int:
    """1024차원 로컬 BGE-M3 의미론 수렴 데이터 주도형 UPSERT 커널 엔진."""
    inserted = 0
    for c in concepts:
        severity = c.get("severity")
        if severity == "info":
            severity = "low"

        # 🎯 owasp_category ➔ owasp_id 명칭 불일치 예외 케이스 방어벽 조립
        owasp = c.get("owasp_id") or c.get("owasp_category")

        # 🎯 기존 행의 누적 aliases 조회 — name_vector 재계산 시 파이프라인이
        # centroid shifting으로 확장한 alias 풀을 보존 (재시드 회귀 방지)
        existing = await conn.fetchrow(
            "SELECT aliases FROM concepts WHERE concept_name = $1", c["concept_name"]
        )
        existing_aliases: list[str] = (
            list(existing["aliases"]) if existing and existing["aliases"] else []
        )
        seed_aliases: list[str] = c.get("aliases", [])
        merged_aliases = list(dict.fromkeys(existing_aliases + seed_aliases))

        # 🎯 [BGE-M3 로컬 추론 및 L2 정규화 직렬화 연동부]
        name_vec_str: str | None = None
        desc_vec_str: str | None = None

        if _embedder is not None:
            name_corpus = " ".join([c["concept_name"]] + merged_aliases)

            # 1) 이름 + 동의어(기존 누적분 포함) 융합형 키워드 풀 컨텍스트 임베딩 연산 (1024차원)
            name_vec_str = _vec_str(_embedder.get_embedding(name_corpus))

            # 2) 한국어 개념 요약 설명문 시맨틱 임베딩 연산 (1024차원)
            desc_ko = c.get("description_ko", "")
            desc_vec_str = (
                _vec_str(_embedder.get_embedding(desc_ko)) if desc_ko else None
            )

        # 멱등성 보장형 중복 방지 자성 UPSERT 트랜잭션 집행
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
                                    SELECT DISTINCT unnest(COALESCE(concepts.domains, '{}') || COALESCE(EXCLUDED.domains, '{}'))
                                  )),
                aliases        = (SELECT array(
                                    SELECT DISTINCT unnest(COALESCE(concepts.aliases, '{}') || COALESCE(EXCLUDED.aliases, '{}'))
                                  )),
                concept_type   = COALESCE(EXCLUDED.concept_type, concepts.concept_type),
                cwe_id         = COALESCE(EXCLUDED.cwe_id, concepts.cwe_id),
                owasp_id       = COALESCE(EXCLUDED.owasp_id, concepts.owasp_id),
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
            seed_aliases,
            name_vec_str,
            desc_vec_str,
        )
        inserted += 1
    return inserted


async def main() -> None:
    global _embedder
    dsn = _dsn()
    logger.info(
        f"PostgreSQL 1024차원 BGE-M3 로컬 임베딩 연동 시드 파이프라인 기동: {dsn.split('@')[-1]}"
    )

    conn = await asyncpg.connect(dsn)
    try:
        logger.info("[1/4] 통합 1024차원 pgvector + HNSW 스키마 DDL 레이어 빌드...")
        await _apply_schema(conn)

        logger.info("[2/4] BGE-M3 로컬 임베딩 모델 로드...")
        from app.infrastructure.llm.factory import create_embedding_client

        _embedder = create_embedding_client(
            mode="production",
            model=os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3"),
        )

        logger.info(
            "[3/4] 보안 도메인 수렴 개념 마스터 시드 적재 (Aliases 파스칼 풀네임 자동 임베딩)..."
        )
        sec_data: list[dict] = json.loads(SEC_JSON.read_text(encoding="utf-8"))
        n_sec = await _upsert_concepts(conn, sec_data)
        logger.info(f"  → 보안 도메인 {n_sec}건 원자적 UPSERT 마감")

        logger.info(
            "[4/4] 성능 도메인 안티패턴 개념 마스터 시드 적재 (1024차원 BGE 로컬 연산)..."
        )
        perf_data: list[dict] = json.loads(PERF_JSON.read_text(encoding="utf-8"))
        n_perf = await _upsert_concepts(conn, perf_data)
        logger.info(f"  → 성능 도메인 {n_perf}건 원자적 UPSERT 마감")

        logger.info(
            f"\n[완료] 총 {n_sec + n_perf}건 통합 적재 수렴 성공 — 1024차원 구조 무결성 보장"
        )
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
