"""C1 통합 테스트 — PostgreSQL DDL + Neo4j Tag Node.

T03: documents UPSERT 멱등성 — 동일 doc_id를 두 번 삽입해도 1행만 존재
T04: Neo4j Tag Node MERGE 멱등성 — 동일 Cypher를 두 번 실행해도 노드 1개만 존재
"""
import uuid
import pytest


# ── T03: PostgreSQL UPSERT 멱등성 ──────────────────────────────────────────

def _ensure_tables(cursor):
    """테스트 실행 전 테이블이 없으면 생성."""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id          SERIAL PRIMARY KEY,
            doc_id      VARCHAR(255) UNIQUE NOT NULL,
            url         TEXT        NOT NULL,
            prefix      VARCHAR(10) NOT NULL DEFAULT 'EXT',
            status      VARCHAR(20) NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active','superseded')),
            etag        VARCHAR(255),
            content_hash VARCHAR(64),
            crawled_at  TIMESTAMPTZ,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


def test_T03_document_upsert_idempotency(pg_cursor):
    """Arrange: 고유 doc_id 준비.
    Act: 동일 doc_id로 INSERT … ON CONFLICT DO UPDATE 2회 실행.
    Assert: 행 1개만 존재, 2회차 updated_at >= 1회차 updated_at.
    """
    _ensure_tables(pg_cursor)

    doc_id = f"EXT_test-upsert_{uuid.uuid4().hex[:8]}"
    url = "https://example.com/test"

    upsert_sql = """
        INSERT INTO documents (doc_id, url, prefix, updated_at)
        VALUES (%s, %s, 'EXT', NOW())
        ON CONFLICT (doc_id) DO UPDATE
            SET url        = EXCLUDED.url,
                updated_at = NOW()
        RETURNING updated_at
    """

    # Arrange — Act 1회차
    pg_cursor.execute(upsert_sql, (doc_id, url))
    first_updated = pg_cursor.fetchone()[0]

    # Act 2회차 (동일 doc_id)
    pg_cursor.execute(upsert_sql, (doc_id, url))
    second_updated = pg_cursor.fetchone()[0]

    # Assert: 행 1개
    pg_cursor.execute("SELECT COUNT(*) FROM documents WHERE doc_id = %s", (doc_id,))
    count = pg_cursor.fetchone()[0]
    assert count == 1, f"UPSERT 후 행이 {count}개여야 1개"

    # Assert: 2회차 updated_at >= 1회차
    assert second_updated >= first_updated, "2회차 updated_at이 1회차보다 이전일 수 없음"


def test_T03_document_upsert_url_update(pg_cursor):
    """Arrange: 기존 문서에 새 URL로 재크롤.
    Act: ON CONFLICT DO UPDATE로 url 갱신.
    Assert: url이 새 값으로 변경됨.
    """
    _ensure_tables(pg_cursor)

    doc_id = f"EXT_test-url-upd_{uuid.uuid4().hex[:8]}"
    old_url = "https://example.com/old"
    new_url = "https://example.com/new"

    pg_cursor.execute(
        "INSERT INTO documents (doc_id, url) VALUES (%s, %s)", (doc_id, old_url)
    )
    pg_cursor.execute(
        """INSERT INTO documents (doc_id, url, updated_at)
           VALUES (%s, %s, NOW())
           ON CONFLICT (doc_id) DO UPDATE SET url = EXCLUDED.url, updated_at = NOW()""",
        (doc_id, new_url),
    )

    pg_cursor.execute("SELECT url FROM documents WHERE doc_id = %s", (doc_id,))
    stored_url = pg_cursor.fetchone()[0]
    assert stored_url == new_url


# ── T04: Neo4j Tag Node MERGE 멱등성 ───────────────────────────────────────

_MERGE_CONCEPT_CYPHER = """
MERGE (c:Concept {name: $name})
  ON CREATE SET c.severity = $severity, c.domain = $domain, c.created = timestamp()
  ON MATCH  SET c.updated  = timestamp()
MERGE (t:Tag {name: $tag_name})
MERGE (c)-[:TAGGED_WITH]->(t)
RETURN c.name AS concept, t.name AS tag
"""

_CLEANUP_CYPHER = """
MATCH (c:Concept {name: $name})-[:TAGGED_WITH]->(t:Tag {name: $tag_name})
DETACH DELETE c, t
"""


def test_T04_tag_node_merge_idempotent(neo4j_driver):
    """Arrange: 고유 개념 이름으로 테스트 데이터 준비.
    Act: 동일 MERGE Cypher를 2회 실행.
    Assert: Concept 노드 1개, Tag 노드 1개, TAGGED_WITH 엣지 1개만 존재.
    """
    concept_name = f"TestXSS_{uuid.uuid4().hex[:6]}"
    tag_name = "Security"
    params = {
        "name": concept_name,
        "severity": "high",
        "domain": "security",
        "tag_name": tag_name,
    }

    with neo4j_driver.session() as session:
        try:
            # Act 1회차
            session.run(_MERGE_CONCEPT_CYPHER, **params)
            # Act 2회차 (동일 파라미터)
            session.run(_MERGE_CONCEPT_CYPHER, **params)

            # Assert: Concept 노드 수
            c_count = session.run(
                "MATCH (c:Concept {name: $name}) RETURN count(c) AS n",
                name=concept_name,
            ).single()["n"]
            assert c_count == 1, f"Concept 노드가 {c_count}개 — MERGE 멱등성 실패"

            # Assert: Tag 노드 수
            t_count = session.run(
                "MATCH (t:Tag {name: $name}) RETURN count(t) AS n",
                name=tag_name,
            ).single()["n"]
            assert t_count >= 1, "Tag 노드가 존재해야 함"

            # Assert: TAGGED_WITH 엣지 수 (이 Concept→Tag 쌍)
            e_count = session.run(
                """MATCH (c:Concept {name: $cname})-[r:TAGGED_WITH]->(t:Tag {name: $tname})
                   RETURN count(r) AS n""",
                cname=concept_name,
                tname=tag_name,
            ).single()["n"]
            assert e_count == 1, f"TAGGED_WITH 엣지가 {e_count}개 — 중복 생성됨"

        finally:
            session.run(_CLEANUP_CYPHER, name=concept_name, tag_name=tag_name)


def test_T04_tag_node_multi_domain(neo4j_driver):
    """Arrange: 동일 개념이 Security + Performance 두 도메인 태그를 가짐.
    Act: 두 태그 각각 MERGE.
    Assert: Concept 1개, TAGGED_WITH 엣지 2개, 각 Tag 1개.
    """
    concept_name = f"TestMemoryLeak_{uuid.uuid4().hex[:6]}"

    with neo4j_driver.session() as session:
        try:
            for tag in ("Security", "Performance"):
                session.run(
                    _MERGE_CONCEPT_CYPHER,
                    name=concept_name,
                    severity="medium",
                    domain="both",
                    tag_name=tag,
                )

            c_count = session.run(
                "MATCH (c:Concept {name: $name}) RETURN count(c) AS n",
                name=concept_name,
            ).single()["n"]
            assert c_count == 1, "Concept 노드는 1개여야 함 (multi-tag MERGE)"

            e_count = session.run(
                "MATCH (c:Concept {name: $name})-[:TAGGED_WITH]->() RETURN count(*) AS n",
                name=concept_name,
            ).single()["n"]
            assert e_count == 2, f"TAGGED_WITH 엣지가 {e_count}개 — 2개여야 함"

        finally:
            session.run(
                "MATCH (c:Concept {name: $name}) DETACH DELETE c",
                name=concept_name,
            )
