"""KMS 파이프라인 4대 스토리지 헬스 체크.

PostgreSQL / pgVector / Neo4j / GCS 각각 최근 데이터가 정상 존재하는지 확인한다.

실행:
    docker exec -it <m0-container> python /app/service/check_storage_health.py
    또는
    uv run python check_storage_health.py  (backend/m0 디렉터리에서)
"""

import asyncio
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

# ── 환경변수 기반 접속 정보 ────────────────────────────────────────────────────
DB_HOST     = os.getenv("DB_HOST", "cloud-sql-proxy")
DB_PORT     = int(os.getenv("DB_PORT", "5432"))
DB_NAME     = os.getenv("DB_NAME", "")
DB_USER     = os.getenv("DB_USER", "")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

NEO4J_URI      = os.getenv("NEO4J_URI", "bolt://host.docker.internal:7687")
NEO4J_USER     = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "codeshepherd")

GCS_BUCKET       = os.getenv("GCS_BUCKET", "")
STORAGE_BACKEND  = os.getenv("STORAGE_BACKEND", "local")

OK   = "✅"
FAIL = "❌"
WARN = "⚠️ "


# ── 1. PostgreSQL + pgVector ──────────────────────────────────────────────────

async def check_postgres():
    print("\n── 1. PostgreSQL + pgVector ─────────────────────────────")
    try:
        import asyncpg
        dsn = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        conn = await asyncpg.connect(dsn, timeout=5)

        # documents
        doc_row = await conn.fetchrow(
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN upload_status IN ('stored','stored_partial') THEN 1 ELSE 0 END) AS stored, "
            "SUM(CASE WHEN neo4j_synced THEN 1 ELSE 0 END) AS neo4j_synced, "
            "SUM(CASE WHEN storage_synced THEN 1 ELSE 0 END) AS gcs_synced "
            "FROM documents"
        )
        print(f"{OK} documents — 총 {doc_row['total']}건 | stored={doc_row['stored']} | neo4j_synced={doc_row['neo4j_synced']} | gcs_synced={doc_row['gcs_synced']}")

        # 최근 5건
        recent = await conn.fetch(
            "SELECT title, category, upload_status, neo4j_synced, storage_synced, created_at "
            "FROM documents ORDER BY created_at DESC LIMIT 5"
        )
        for r in recent:
            neo = "N✅" if r["neo4j_synced"] else "N❌"
            gcs = "G✅" if r["storage_synced"] else "G❌"
            print(f"    [{r['upload_status']:16s}] {neo} {gcs}  {r['title'][:40]}  ({r['category']})")

        # chunks
        chunk_row = await conn.fetchrow("SELECT COUNT(*) AS total FROM chunks")
        print(f"{OK} chunks    — 총 {chunk_row['total']}건")

        # chunk_embeddings (pgVector)
        embed_row = await conn.fetchrow(
            "SELECT COUNT(*) AS total, COUNT(DISTINCT model_name) AS models "
            "FROM chunk_embeddings"
        )
        if embed_row["total"] == 0:
            print(f"{FAIL} chunk_embeddings — 0건 (임베딩 미생성)")
        else:
            # 벡터 차원 확인
            dim_row = await conn.fetchrow(
                "SELECT vector_dims(embedding) AS dim FROM chunk_embeddings LIMIT 1"
            )
            dim = dim_row["dim"] if dim_row else "?"
            print(f"{OK} chunk_embeddings — {embed_row['total']}건 | 차원={dim} | 모델 종류={embed_row['models']}")

        await conn.close()

    except Exception as e:
        print(f"{FAIL} PostgreSQL 연결 실패: {e}")


# ── 2. Neo4j ─────────────────────────────────────────────────────────────────

async def check_neo4j():
    print("\n── 2. Neo4j ────────────────────────────────────────────")
    try:
        from neo4j import AsyncGraphDatabase
        driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

        async with driver.session() as s:
            # 노드 수
            doc_r    = await s.run("MATCH (d:Document) RETURN count(d) AS n")
            chunk_r  = await s.run("MATCH (c:Chunk) RETURN count(c) AS n")
            entity_r = await s.run("MATCH (e:Entity) RETURN count(e) AS n")
            cat_r    = await s.run("MATCH (c:Category) RETURN count(c) AS n")
            rel_r    = await s.run("MATCH ()-[r]->() RETURN count(r) AS n")

            doc_n    = (await doc_r.single())["n"]
            chunk_n  = (await chunk_r.single())["n"]
            entity_n = (await entity_r.single())["n"]
            cat_n    = (await cat_r.single())["n"]
            rel_n    = (await rel_r.single())["n"]

            status = OK if doc_n > 0 else FAIL
            print(f"{status} Document={doc_n} | Chunk={chunk_n} | Entity={entity_n} | Category={cat_n} | 관계={rel_n}")

            # 최근 5개 문서
            recent_r = await s.run(
                "MATCH (d:Document) RETURN d.doc_id AS id, d.title AS title, d.category AS cat "
                "ORDER BY d.doc_id DESC LIMIT 5"
            )
            records = await recent_r.data()
            for r in records:
                print(f"    [{r['cat']:14}] {r['title'][:40]}")

        await driver.close()

    except Exception as e:
        print(f"{FAIL} Neo4j 연결 실패: {e}")


# ── 3. GCS ───────────────────────────────────────────────────────────────────

async def check_gcs():
    print("\n── 3. GCS / Storage ────────────────────────────────────")

    if STORAGE_BACKEND == "local":
        # 로컬 스토리지 확인
        local_root = os.getenv("LOCAL_STORAGE_PATH", "/tmp/kms_storage")
        if not os.path.exists(local_root):
            print(f"{WARN} LOCAL_STORAGE_PATH={local_root} 없음 (아직 업로드 없거나 경로 불일치)")
            return
        files = []
        for dirpath, _, filenames in os.walk(local_root):
            for f in filenames:
                files.append(os.path.join(dirpath, f))
        print(f"{OK} Local Storage ({local_root}) — {len(files)}개 파일")
        for f in sorted(files)[-5:]:
            print(f"    {f[len(local_root):]}")
        return

    if not GCS_BUCKET:
        print(f"{WARN} GCS_BUCKET 환경변수 미설정")
        return

    try:
        from google.cloud import storage as gcs
        client = gcs.Client()
        bucket = client.bucket(GCS_BUCKET)

        # originals / markdown / images 각 prefix별 파일 수
        for prefix in ("originals/", "markdown/", "images/"):
            blobs = list(client.list_blobs(GCS_BUCKET, prefix=prefix, max_results=100))
            status = OK if blobs else WARN
            print(f"{status} gs://{GCS_BUCKET}/{prefix} — {len(blobs)}개")

        # 전체 최근 5개
        all_blobs = sorted(
            client.list_blobs(GCS_BUCKET, max_results=200),
            key=lambda b: b.updated,
            reverse=True,
        )[:5]
        print(f"{OK} 최근 업로드 파일:")
        for b in all_blobs:
            print(f"    {b.name}  ({b.size // 1024}KB)")

    except Exception as e:
        print(f"{FAIL} GCS 접근 실패: {e}")


# ── 4. 요약 ──────────────────────────────────────────────────────────────────

async def main():
    print("=" * 56)
    print("  KMS 파이프라인 스토리지 헬스 체크")
    print("=" * 56)
    print(f"  DB:     {DB_HOST}:{DB_PORT}/{DB_NAME}")
    print(f"  Neo4j:  {NEO4J_URI}")
    print(f"  GCS:    {'gs://' + GCS_BUCKET if GCS_BUCKET else 'local (' + STORAGE_BACKEND + ')'}")

    await check_postgres()
    await check_neo4j()
    await check_gcs()

    print("\n" + "=" * 56)
    print("  체크 완료")
    print("=" * 56)


asyncio.run(main())
