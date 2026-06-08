"""TDD: _validate_sql_v2 — LLM 생성 SQL 방어 (chat_routes).

보안 critical 함수. SELECT 단일문 + LIMIT + 허용 테이블만 통과시키고
모든 data-modifying / injection 패턴을 차단해야 한다.
"""

import pytest

from app.routes.chat_routes import _validate_sql_v2


# ---------------------------------------------------------------------------
# 통과해야 하는 정상 쿼리 (True)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sql", [
    "SELECT content FROM documents LIMIT 5",
    "SELECT d.title FROM documents d LIMIT 10",
    "SELECT c.content FROM chunks c WHERE c.doc_id IS NOT NULL LIMIT 3",
    "SELECT content FROM documents WHERE doc_id IN (SELECT doc_id FROM chunks) LIMIT 5",
])
def test_valid_select_passes(sql):
    assert _validate_sql_v2(sql) is True


# ---------------------------------------------------------------------------
# 차단해야 하는 쿼리 (False)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sql", [
    "",                                                              # 빈 문자열
    "   ",                                                           # 공백만
    "NOT A VALID SQL @#$",                                           # parse 에러
    "SELECT * FROM documents",                                       # LIMIT 누락
    "SELECT * FROM documents LIMIT 1; DROP TABLE documents",         # stacked query
    "SELECT title FROM documents UNION SELECT content FROM chunks LIMIT 5",  # UNION
    "INSERT INTO documents (title) VALUES ('x')",                    # INSERT 단독
    "UPDATE documents SET title='x' WHERE doc_id='1'",              # UPDATE 단독
    "DELETE FROM documents WHERE doc_id='1'",                       # DELETE 단독
    "DROP TABLE documents",                                          # DROP
    "SELECT * FROM users LIMIT 5",                                   # 비허용 테이블
    "SELECT password FROM auth_users LIMIT 1",                      # 비허용 테이블2
    "SELECT * FROM documents WHERE doc_id IN (SELECT id FROM users) LIMIT 1",  # subquery 비허용
    "SELECT 1 LIMIT 1",                                             # 테이블 없음
])
def test_dangerous_sql_blocked(sql):
    assert _validate_sql_v2(sql) is False


# ---------------------------------------------------------------------------
# 🔴 CTE 이름 위장 data-modifying 공격 — 반드시 차단 (False)
# 발견된 취약점: CTE 이름을 허용 테이블명으로 지으면 내부 DML이 우회됨
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sql", [
    # CTE 이름을 'documents'로 위장 → 내부 DELETE
    "WITH documents AS (DELETE FROM chunks RETURNING chunk_id) SELECT * FROM documents LIMIT 1",
    # CTE 이름을 'chunks'로 위장 → 내부 UPDATE
    "WITH chunks AS (UPDATE documents SET title=NULL RETURNING doc_id) SELECT * FROM chunks LIMIT 1",
    # CTE 이름을 'documents'로 위장 → 내부 INSERT
    "WITH documents AS (INSERT INTO chunks(content) VALUES('x') RETURNING chunk_id) SELECT * FROM documents LIMIT 1",
])
def test_cte_disguised_dml_blocked(sql):
    assert _validate_sql_v2(sql) is False, (
        "CTE 이름 위장 data-modifying 공격이 차단되지 않았습니다 — "
        "_validate_sql_v2가 SELECT 하위의 DELETE/UPDATE/INSERT를 탐지해야 합니다."
    )
