"""P1-T1 통합 테스트 — PostgreSQL DDL v2 (PRD-schema.md §15.2).

T01: documents 테이블 — state CHECK 제약 및 UPSERT 멱등성
T02: staging_concepts 테이블 — concept_json JSONB, state CHECK 제약
T03: concepts 테이블 — concept_name UNIQUE, domain/severity CHECK 제약
T04: pipeline_logs 테이블 — level CHECK 제약
T05: concept_snapshots 테이블 — raw_output_json JSONB 적재
"""

import uuid
import json
import pytest
import psycopg2


def _apply_schema(cursor):
    """테스트 DB에 v2 DDL 적용 (idempotent)."""
    from pathlib import Path
    sql = (
        Path(__file__).parent.parent.parent
        / "scripts" / "seed" / "security" / "schema.sql"
    ).read_text(encoding="utf-8")
    cursor.execute(sql)


# ── T01: documents ─────────────────────────────────────────────────────────


def test_T01_documents_upsert_idempotent(pg_cursor):
    """Arrange: 고유 doc_id + 필수 컬럼 준비.
    Act: 동일 doc_id로 INSERT ON CONFLICT DO UPDATE 2회.
    Assert: 행 1개, 2회차 updated_at >= 1회차.
    """
    _apply_schema(pg_cursor)

    doc_id = f"EXT_test-upsert_{uuid.uuid4().hex[:8]}"
    upsert = """
        INSERT INTO documents (doc_id, source_prefix, original_url, content_hash, updated_at)
        VALUES (%s, 'EXT', 'https://example.com', 'deadbeef', now())
        ON CONFLICT (doc_id) DO UPDATE
          SET updated_at = now()
        RETURNING updated_at
    """

    pg_cursor.execute(upsert, (doc_id,))
    t1 = pg_cursor.fetchone()[0]

    pg_cursor.execute(upsert, (doc_id,))
    t2 = pg_cursor.fetchone()[0]

    pg_cursor.execute("SELECT COUNT(*) FROM documents WHERE doc_id=%s", (doc_id,))
    assert pg_cursor.fetchone()[0] == 1, "UPSERT 후 행이 1개여야 함"
    assert t2 >= t1, "2회차 updated_at이 1회차보다 이전일 수 없음"


def test_T01_documents_state_check(pg_cursor):
    """Arrange: 유효하지 않은 state 값 준비.
    Act: INSERT with state='INVALID'.
    Assert: IntegrityError (CHECK 제약 위반).
    """
    _apply_schema(pg_cursor)

    doc_id = f"EXT_invalid-state_{uuid.uuid4().hex[:8]}"
    with pytest.raises(psycopg2.errors.CheckViolation):
        pg_cursor.execute(
            """INSERT INTO documents
               (doc_id, source_prefix, original_url, content_hash, state)
               VALUES (%s, 'EXT', 'https://x.com', 'abcd1234', 'INVALID')""",
            (doc_id,),
        )


def test_T01_documents_infer_confidence_default(pg_cursor):
    """Arrange: infer_confidence 미지정.
    Act: INSERT documents.
    Assert: infer_confidence = 0 (DEFAULT).
    """
    _apply_schema(pg_cursor)

    doc_id = f"EXT_conf-default_{uuid.uuid4().hex[:8]}"
    pg_cursor.execute(
        "INSERT INTO documents (doc_id, source_prefix, original_url, content_hash) VALUES (%s,'EXT','https://x.com','ab12ef34')",
        (doc_id,),
    )
    pg_cursor.execute("SELECT infer_confidence FROM documents WHERE doc_id=%s", (doc_id,))
    assert pg_cursor.fetchone()[0] == 0.0


# ── T02: staging_concepts ──────────────────────────────────────────────────


def _insert_doc(cursor, doc_id="EXT_seed_0000abcd"):
    cursor.execute(
        "INSERT INTO documents (doc_id, source_prefix, original_url, content_hash) "
        "VALUES (%s,'EXT','https://docs.example.com','0000abcd') ON CONFLICT DO NOTHING",
        (doc_id,),
    )
    return doc_id


def test_T02_staging_concept_json_stored(pg_cursor):
    """Arrange: documents 선행 삽입 후 concept_json 준비.
    Act: staging_concepts INSERT.
    Assert: concept_json JSONB 필드 완전 복원.
    """
    _apply_schema(pg_cursor)
    doc_id = _insert_doc(pg_cursor)

    session_id = uuid.uuid4()
    concept = {
        "concept_name": "XSS",
        "concept_domain": "security",
        "severity": "HIGH",
        "cwe_id": "CWE-79",
    }

    pg_cursor.execute(
        "INSERT INTO staging_concepts (session_id, doc_id, concept_json) VALUES (%s,%s,%s) RETURNING id",
        (str(session_id), doc_id, json.dumps(concept)),
    )
    row_id = pg_cursor.fetchone()[0]

    pg_cursor.execute("SELECT concept_json FROM staging_concepts WHERE id=%s", (str(row_id),))
    stored = pg_cursor.fetchone()[0]
    assert stored["concept_name"] == "XSS"
    assert stored["concept_domain"] == "security"


def test_T02_staging_state_default_draft(pg_cursor):
    """Arrange: state 미지정.
    Act: INSERT staging_concepts.
    Assert: state = 'DRAFT'.
    """
    _apply_schema(pg_cursor)
    doc_id = _insert_doc(pg_cursor, f"EXT_state-default_{uuid.uuid4().hex[:8]}")

    pg_cursor.execute(
        "INSERT INTO staging_concepts (session_id, doc_id, concept_json) VALUES (%s,%s,%s) RETURNING state",
        (str(uuid.uuid4()), doc_id, json.dumps({"concept_name": "CSRF"})),
    )
    assert pg_cursor.fetchone()[0] == "DRAFT"


def test_T02_staging_state_check(pg_cursor):
    """Arrange: 유효하지 않은 state 값.
    Act: INSERT staging_concepts with state='WRONG'.
    Assert: CheckViolation.
    """
    _apply_schema(pg_cursor)
    doc_id = _insert_doc(pg_cursor, f"EXT_staging-check_{uuid.uuid4().hex[:8]}")

    with pytest.raises(psycopg2.errors.CheckViolation):
        pg_cursor.execute(
            "INSERT INTO staging_concepts (session_id, doc_id, concept_json, state) VALUES (%s,%s,%s,'WRONG')",
            (str(uuid.uuid4()), doc_id, json.dumps({"concept_name": "SQLi"})),
        )


# ── T03: concepts ──────────────────────────────────────────────────────────


def test_T03_concepts_unique_name(pg_cursor):
    """Arrange: concept_name 'XSS'.
    Act: 동일 concept_name 두 번 INSERT.
    Assert: UniqueViolation.
    """
    _apply_schema(pg_cursor)

    pg_cursor.execute(
        "INSERT INTO concepts (concept_name, concept_domain) VALUES ('XSS_UNIQ_TEST','security') ON CONFLICT DO NOTHING"
    )
    with pytest.raises(psycopg2.errors.UniqueViolation):
        pg_cursor.execute(
            "INSERT INTO concepts (concept_name, concept_domain) VALUES ('XSS_UNIQ_TEST','security')"
        )


def test_T03_concepts_domain_check(pg_cursor):
    """Arrange: 유효하지 않은 concept_domain.
    Act: INSERT concepts with domain='unknown'.
    Assert: CheckViolation.
    """
    _apply_schema(pg_cursor)

    with pytest.raises(psycopg2.errors.CheckViolation):
        pg_cursor.execute(
            "INSERT INTO concepts (concept_name, concept_domain) VALUES ('BadDomain_test','unknown')"
        )


def test_T03_concepts_severity_check(pg_cursor):
    """Arrange: 유효하지 않은 severity.
    Act: INSERT concepts with severity='EXTREME'.
    Assert: CheckViolation.
    """
    _apply_schema(pg_cursor)

    with pytest.raises(psycopg2.errors.CheckViolation):
        pg_cursor.execute(
            "INSERT INTO concepts (concept_name, concept_domain, severity) VALUES ('SevCheck_test','security','EXTREME')"
        )


# ── T04: pipeline_logs ─────────────────────────────────────────────────────


def test_T04_pipeline_logs_level_check(pg_cursor):
    """Arrange: 유효하지 않은 level.
    Act: INSERT pipeline_logs with level='DEBUG'.
    Assert: CheckViolation.
    """
    _apply_schema(pg_cursor)
    doc_id = _insert_doc(pg_cursor, f"EXT_logs-level_{uuid.uuid4().hex[:8]}")

    with pytest.raises(psycopg2.errors.CheckViolation):
        pg_cursor.execute(
            "INSERT INTO pipeline_logs (doc_id, agent, level, message) VALUES (%s,'Crawler','DEBUG','msg')",
            (doc_id,),
        )


def test_T04_pipeline_logs_insert_ok(pg_cursor):
    """Arrange: 유효한 level INFO.
    Act: INSERT pipeline_logs.
    Assert: 행 삽입 성공.
    """
    _apply_schema(pg_cursor)
    doc_id = _insert_doc(pg_cursor, f"EXT_logs-ok_{uuid.uuid4().hex[:8]}")

    pg_cursor.execute(
        "INSERT INTO pipeline_logs (doc_id, agent, level, message) VALUES (%s,'Extractor','INFO','추출 완료') RETURNING id",
        (doc_id,),
    )
    assert pg_cursor.fetchone() is not None


# ── T05: concept_snapshots ─────────────────────────────────────────────────


def test_T05_concept_snapshots_jsonb(pg_cursor):
    """Arrange: raw_output_json JSONB 페이로드.
    Act: INSERT concept_snapshots.
    Assert: raw_output_json 복원 정확.
    """
    _apply_schema(pg_cursor)
    doc_id = _insert_doc(pg_cursor, f"EXT_snap_{uuid.uuid4().hex[:8]}")

    raw = {"concept_name": "MemoryLeak", "concept_domain": "both", "severity": "HIGH"}
    pg_cursor.execute(
        "INSERT INTO concept_snapshots (doc_id, session_id, raw_output_json) VALUES (%s,%s,%s) RETURNING id",
        (doc_id, str(uuid.uuid4()), json.dumps(raw)),
    )
    row_id = pg_cursor.fetchone()[0]

    pg_cursor.execute("SELECT raw_output_json FROM concept_snapshots WHERE id=%s", (str(row_id),))
    stored = pg_cursor.fetchone()[0]
    assert stored["concept_name"] == "MemoryLeak"
    assert stored["concept_domain"] == "both"
