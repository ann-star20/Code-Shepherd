import asyncio, asyncpg, os, sys
sys.stdout.reconfigure(encoding="utf-8")

DOC_ID = "f10085ad-d9fc-4cc7-86c3-2478cbb6ccd2"

async def main():
    dsn = (
        f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
        f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT', 5432)}/{os.getenv('DB_NAME')}"
    )
    conn = await asyncpg.connect(dsn)

    # documents
    doc = await conn.fetchrow("SELECT * FROM documents WHERE doc_id = $1", DOC_ID)
    if not doc:
        print("❌ documents 테이블에 없음")
        await conn.close()
        return

    print("=== PostgreSQL: documents ===")
    important = ["doc_id", "title", "category", "upload_status", "file_type",
                 "parser_used", "neo4j_synced", "storage_synced",
                 "quality_score", "metadata_score", "created_at"]
    for k in important:
        print(f"  {k:20}: {doc[k]}")

    # chunks
    chunks = await conn.fetch(
        "SELECT chunk_id, chunk_type, token_count, section_header, chunk_index "
        "FROM chunks WHERE doc_id = $1 ORDER BY chunk_index",
        DOC_ID,
    )
    print(f"\n=== PostgreSQL: chunks ({len(chunks)}건) ===")
    for c in chunks:
        print(f"  [{c['chunk_type']:6}] idx={c['chunk_index']}  {c['token_count']}tok  {str(c['section_header'] or '')[:40]}")

    # chunk_embeddings
    emb = await conn.fetchrow(
        "SELECT COUNT(*) AS n, MIN(vector_dims(embedding)) AS dim, "
        "MAX(model_name) AS model "
        "FROM chunk_embeddings "
        "WHERE chunk_id IN (SELECT chunk_id FROM chunks WHERE doc_id = $1)",
        DOC_ID,
    )
    status = "✅" if emb["n"] > 0 else "❌"
    print(f"\n=== pgVector: chunk_embeddings ===")
    print(f"  {status} {emb['n']}건 | 차원={emb['dim']} | 모델={emb['model']}")

    await conn.close()

    # Neo4j
    print("\n=== Neo4j ===")
    try:
        from neo4j import AsyncGraphDatabase
        neo4j_uri  = os.getenv("NEO4J_URI", "bolt://host.docker.internal:7687")
        neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        neo4j_pw   = os.getenv("NEO4J_PASSWORD", "codeshepherd")
        driver = AsyncGraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_pw))
        async with driver.session() as s:
            r = await s.run(
                "MATCH (d:Document {doc_id: $id}) "
                "OPTIONAL MATCH (d)-[:HAS_CHUNK]->(c:Chunk) "
                "OPTIONAL MATCH (d)-[:COVERS]->(e:Entity) "
                "RETURN d.title AS title, d.category AS cat, "
                "count(DISTINCT c) AS chunks, count(DISTINCT e) AS entities",
                id=DOC_ID,
            )
            rec = await r.single()
        if rec and rec["title"]:
            print(f"  ✅ Document 노드 존재")
            print(f"     title={rec['title']}")
            print(f"     category={rec['cat']}")
            print(f"     Chunk 노드={rec['chunks']}개, Entity 노드={rec['entities']}개")
        else:
            print("  ❌ Neo4j에 Document 노드 없음")
        await driver.close()
    except Exception as e:
        print(f"  ❌ Neo4j 연결 실패: {e}")

asyncio.run(main())
