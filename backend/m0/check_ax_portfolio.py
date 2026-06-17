import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from dotenv import load_dotenv
load_dotenv("../../.env")

from neo4j import GraphDatabase

URI  = os.getenv("NEO4J_URI")
USER = os.getenv("NEO4J_USER")
PASS = os.getenv("NEO4J_PASSWORD")

driver = GraphDatabase.driver(URI, auth=(USER, PASS))

TARGET = "AX PORTFOLIO"

with driver.session() as s:

    # 1. Document 노드 기본 정보
    r = s.run("""
        MATCH (d:Document)
        WHERE d.title CONTAINS $title OR d.doc_id = $title
        RETURN d.doc_id AS doc_id, d.title AS title,
               d.category AS category, d.doc_complexity AS complexity
        LIMIT 5
    """, title=TARGET)
    rows = r.data()
    print("─── Document 노드 ───────────────────────")
    for row in rows:
        print(f"  doc_id   : {row['doc_id']}")
        print(f"  title    : {row['title']}")
        print(f"  category : {row['category']}")
        print(f"  complexity: {row['complexity']}")
    if not rows:
        print("  ⚠  Document 노드를 찾을 수 없습니다.")
        driver.close(); sys.exit()

    doc_id = rows[0]["doc_id"]

    # 2. 청크 수
    r = s.run("""
        MATCH (d:Document {doc_id:$doc_id})-[:HAS_CHUNK]->(c:Chunk)
        RETURN count(c) AS total,
               sum(CASE WHEN c.chunk_type='parent' THEN 1 ELSE 0 END) AS parent,
               sum(CASE WHEN c.chunk_type='child'  THEN 1 ELSE 0 END) AS child
    """, doc_id=doc_id)
    row = r.single()
    print(f"\n─── Chunk ───────────────────────────────")
    print(f"  총 청크   : {row['total']} (parent {row['parent']} / child {row['child']})")

    # 3. 카테고리
    r = s.run("""
        MATCH (d:Document {doc_id:$doc_id})-[:BELONGS_TO]->(cat:Category)
        RETURN cat.name AS cat
    """, doc_id=doc_id)
    cats = [x["cat"] for x in r.data()]
    print(f"\n─── Category ────────────────────────────")
    print(f"  {cats}")

    # 4. 추출된 Entity (상위 10개)
    r = s.run("""
        MATCH (d:Document {doc_id:$doc_id})-[:HAS_CHUNK]->(c:Chunk)-[:MENTIONS]->(e:Entity)
        RETURN e.name AS name, e.type AS type, count(c) AS cnt
        ORDER BY cnt DESC LIMIT 10
    """, doc_id=doc_id)
    entities = r.data()
    print(f"\n─── Entity (상위 10개) ───────────────────")
    for e in entities:
        print(f"  [{e['type']:12s}] {e['name']} — {e['cnt']}개 청크에서 언급")

    # 5. COVERS 관계 (Document→Entity 직접 연결)
    r = s.run("""
        MATCH (d:Document {doc_id:$doc_id})-[:COVERS]->(e:Entity)
        RETURN count(e) AS cnt
    """, doc_id=doc_id)
    print(f"\n─── COVERS 관계 ─────────────────────────")
    print(f"  Document→Entity COVERS : {r.single()['cnt']}개")

    # 6. SHARES_ENTITY (연관 문서)
    r = s.run("""
        MATCH (d:Document {doc_id:$doc_id})-[:SHARES_ENTITY {via: e_name}]-(d2:Document)
        WITH d2.title AS related, collect(DISTINCT e_name) AS via
        RETURN related, via LIMIT 5
    """, doc_id=doc_id)
    # via가 없으면 다른 방법으로
    r2 = s.run("""
        MATCH (d:Document {doc_id:$doc_id})-[r:SHARES_ENTITY]-(d2:Document)
        RETURN d2.title AS related, r.via AS via
        LIMIT 10
    """, doc_id=doc_id)
    shared = r2.data()
    print(f"\n─── SHARES_ENTITY (연관 문서) ───────────")
    if shared:
        for x in shared:
            print(f"  ↔ {x['related']}  (via: {x['via']})")
    else:
        print("  (연관 문서 없음 또는 아직 생성 전)")

    # 7. 전체 관계 타입별 집계
    r = s.run("""
        MATCH (d:Document {doc_id:$doc_id})-[rel]->()
        RETURN type(rel) AS rel_type, count(rel) AS cnt
        ORDER BY cnt DESC
    """, doc_id=doc_id)
    print(f"\n─── 전체 관계 집계 (Document 기준) ──────")
    for row in r.data():
        print(f"  {row['rel_type']:20s} : {row['cnt']}")

driver.close()
