"""review_issue 적재 TDD — m3 분석 이슈(test_verification·performance)를
dev4 공용 테이블 review_issue 에 한 행씩 적재한다.

격리: tempfile SQLite + persist.DB_PATH monkeypatch (자격증명 없이 자가검증).
- name_of_function: contracts.Issue 신규 필드(기본 "") + enrich(AST=사실, 키 없이도).
- severity 매핑: Critical→critical / Major→major / Minor→minor (한 dict 로 분리).
- 라운드트립: 14개(매핑상 12개) 내용 컬럼 매핑, pull_request_id·user_id NULL,
  id·created_at DB 기본값 자동 채움.
- DB 실패 시 정직한 skip(예외를 위로 던지지 않음).
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import textwrap

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contracts import AgentOutput, Issue, SummaryCount  # noqa: E402
import persist as p  # noqa: E402


# ════════════════════════════════════════════════════════════════════════
# 1) contracts.Issue.name_of_function — 신규 필드(기본 빈 문자열, 출력계약 불변)
# ════════════════════════════════════════════════════════════════════════
def test_issue_has_name_of_function_default_empty():
    i = Issue(severity="Minor", file="x.py", message="m", rule_id="R")
    assert i.name_of_function == ""


# ════════════════════════════════════════════════════════════════════════
# 2) enrich — issue.name_of_function 를 AST 함수명으로 채움 (LLM 키 없이도)
# ════════════════════════════════════════════════════════════════════════
def _write_repo(tmp_path, code: str) -> str:
    src = tmp_path / "src"
    src.mkdir()
    (src / "f.py").write_text(textwrap.dedent(code), encoding="utf-8")
    return str(tmp_path)


def test_enrich_fills_name_of_function_without_key(tmp_path, monkeypatch):
    from enrich import code_context
    monkeypatch.setattr(code_context, "_has_llm_key", lambda: False)
    repo = _write_repo(tmp_path, """
        def load_cart_items(uid):
            for x in items:
                db.query(x)
    """)
    issue = Issue(severity="Major", file="src/f.py", line=3,
                  message="N+1", rule_id="PERF-002")
    code_context.augment_issues([issue], repo, describe=lambda s: "안 불림")
    assert issue.name_of_function == "load_cart_items"
    # 이름은 AST=사실 → 키 없어도 채움. code_context(LLM)는 키 없으니 빈 값.
    assert issue.code_context == ""


def test_enrich_name_of_function_empty_when_no_function(tmp_path, monkeypatch):
    from enrich import code_context
    monkeypatch.setattr(code_context, "_has_llm_key", lambda: True)
    repo = _write_repo(tmp_path, "X = 1\nY = 2\n")
    issue = Issue(severity="Minor", file="src/f.py", line=1,
                  message="m", rule_id="PERF-001")
    code_context.augment_issues([issue], repo, describe=lambda s: "X")
    assert issue.name_of_function == ""


# ════════════════════════════════════════════════════════════════════════
# 3) severity 매핑 — 한 dict 로 분리(dev4 합의 시 한 곳만 수정)
# ════════════════════════════════════════════════════════════════════════
def test_severity_map_to_db_scale():
    # 실 GCP review_issue CHECK 허용값 = critical/high/medium/low (확인됨).
    # m3 3단계 → 그 4단계로 매핑(Minor→medium; dev4 합의 시 이 dict 한 곳만 수정).
    assert p.REVIEW_SEVERITY_MAP["Critical"] == "critical"
    assert p.REVIEW_SEVERITY_MAP["Major"] == "high"
    assert p.REVIEW_SEVERITY_MAP["Minor"] == "medium"


# ════════════════════════════════════════════════════════════════════════
# 4) 적재 라운드트립 + 5) 정직한 skip — SQLite 격리
# ════════════════════════════════════════════════════════════════════════
class TestReviewIssuePersist:
    def setup_method(self):
        self._tf = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._db_path = self._tf.name
        self._tf.close()
        self._orig = p.DB_PATH
        p.DB_PATH = self._db_path

    def teardown_method(self):
        p.DB_PATH = self._orig
        try:
            os.remove(self._db_path)
        except OSError:
            pass

    def _rows(self):
        conn = sqlite3.connect(self._db_path)
        try:
            conn.row_factory = sqlite3.Row
            return conn.execute(
                "SELECT * FROM review_issue ORDER BY agent, github_id"
            ).fetchall()
        finally:
            conn.close()

    def test_roundtrip_maps_content_columns(self):
        issue = Issue(
            severity="Major", file="src/cart.py", line=8, message="N+1",
            rule_id="PERF-002", suggestion="joinedload 사용",
            keyword="성능", sub_category="N+1 쿼리",
            code_context="장바구니 항목 불러오는 함수",
            code_snippet="def load_cart_items(uid):\n    return db.query(uid)",
            github_id="junior_dev_01",
            programming_language="python", framework="django",
            framework_version="4.2", name_of_function="load_cart_items",
        )
        out = AgentOutput(
            task_id="t", scan_id=3, pr_id="P", agent="performance",
            issues=[issue], summary=SummaryCount(major=1),
        )
        p.persist_review_issue([out])

        rows = self._rows()
        assert len(rows) == 1
        r = rows[0]
        # 12개 내용 컬럼이 매핑대로
        assert r["github_id"] == "junior_dev_01"
        assert r["agent"] == "performance"
        assert r["severity"] == "high"           # Major→high (DB 4단계 스케일)
        assert r["keyword"] == "성능"
        assert r["sub_category"] == "N+1 쿼리"
        assert r["code_context"] == "장바구니 항목 불러오는 함수"
        assert r["code_snippet"].startswith("def load_cart_items")
        assert r["suggestion"] == "joinedload 사용"
        assert r["programming_language"] == "python"
        assert r["framework"] == "django"
        assert r["framework_version"] == "4.2"
        assert r["name_of_function"] == "load_cart_items"
        # dev4가 채울 컬럼 — m3는 비움(NULL)
        assert r["pull_request_id"] is None
        assert r["user_id"] is None
        # DB 기본값으로 자동 채움
        assert r["id"]
        assert r["created_at"]

    def test_persists_every_issue_of_every_output(self):
        tv = AgentOutput(
            task_id="t", scan_id=1, pr_id="P", agent="test_verification",
            issues=[
                Issue(severity="Major", file="(전체)", message="cov", rule_id="TEST-001"),
                Issue(severity="Minor", file="a.py", line=2, message="no test", rule_id="TEST-004"),
            ],
        )
        perf = AgentOutput(
            task_id="t", scan_id=1, pr_id="P", agent="performance",
            issues=[Issue(severity="Critical", file="a.py", line=3, message="N+1", rule_id="PERF-002")],
        )
        p.persist_review_issue([tv, perf])
        rows = self._rows()
        assert len(rows) == 3
        # Critical→critical, Major→high, Minor→medium
        assert sorted(r["severity"] for r in rows) == ["critical", "high", "medium"]

    def test_db_failure_is_honest_skip(self):
        # 존재하지 않는 디렉터리 → sqlite 연결 실패. 예외를 위로 던지지 않아야.
        p.DB_PATH = os.path.join(self._db_path + "_nope_dir", "x.db")
        out = AgentOutput(
            task_id="t", scan_id=1, pr_id="P", agent="performance",
            issues=[Issue(severity="Minor", file="a.py", line=1, message="m", rule_id="R")],
        )
        p.persist_review_issue([out])  # 예외 없이 조용히 skip (가짜 행 없음)


# ════════════════════════════════════════════════════════════════════════
# 6) Postgres 경로 — persist_pg 와 같은 형태(conn 주입). 실 DB 없이 계약만 검증.
#    실 접속/배선은 [확인 0] dev4 합의 후. 여기선 SQL 모양·파라미터·생략 컬럼 확인.
# ════════════════════════════════════════════════════════════════════════
class _FakeCursor:
    def __init__(self, log):
        self._log = log

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self._log.append((sql, params))


class _FakeConn:
    def __init__(self):
        self.calls: list = []

    def cursor(self):
        return _FakeCursor(self.calls)


def test_pg_insert_links_pr_via_github_pr_number():
    """PG 경로: pull_request_id·user_id 를 pull_requests 에서 github_pr_number 로 링크.

    m3는 내부 pull_request_id 를 모르지만, 아는 GitHub PR 번호로 pull_requests 행을
    찾아 그 행의 id(→pull_request_id)·user_id 를 서브쿼리로 채운다(dev4 합의).
    """
    conn = _FakeConn()
    issue = Issue(
        severity="Major", file="src/cart.py", line=8, message="N+1",
        rule_id="PERF-002", keyword="성능", name_of_function="load_cart_items",
        github_id="junior_dev_01",
    )
    out = AgentOutput(
        task_id="t", scan_id=3, pr_id="P", agent="performance", issues=[issue],
    )
    p.persist_review_issue_pg([out], github_pr_number=42, conn=conn)

    inserts = [(sql, prm) for sql, prm in conn.calls
               if sql.strip().upper().startswith("INSERT")]
    assert len(inserts) == 1
    sql, params = inserts[0]
    low = sql.lower()
    # pull_request_id·user_id 는 pull_requests 행에서 가져옴(서브쿼리 SELECT)
    assert "pull_request_id" in low
    assert "user_id" in low
    assert "pull_requests" in low
    assert "github_pr_number" in low
    # 값은 파라미터 바인딩만(%s) — f-string SQL 금지
    assert "%s" in sql
    assert "42" not in sql                  # PR 번호도 바인딩(SQL에 안 박힘)
    assert "load_cart_items" not in sql
    # id·created_at 은 여전히 DB 기본값(직접 안 넣음)
    assert "created_at" not in low
    # severity 매핑(Major→high) + PR 번호가 파라미터에 들어감
    assert "high" in params
    assert "Major" not in params
    assert 42 in params
    assert "load_cart_items" in params


def test_pg_is_idempotent_delete_then_insert():
    """같은 PR·agent 를 다시 적재해도 중복 행이 안 쌓이게 — 먼저 지우고(DELETE) 넣음.

    review_issue 엔 dedup 키가 없으므로(공용 테이블), 그 PR·그 agent 의 기존 행을
    지운 뒤 INSERT 한다(scan_issues 의 DELETE WHERE scan_id,agent 패턴과 동일).
    """
    conn = _FakeConn()
    issue = Issue(severity="Major", file="a.py", line=3, message="N+1",
                  rule_id="PERF-002", github_id="dev1", name_of_function="f")
    out = AgentOutput(
        task_id="t", scan_id=1, pr_id="P", agent="performance", issues=[issue],
    )
    p.persist_review_issue_pg([out], github_pr_number=42, conn=conn)

    kinds = [sql.strip().split()[0].upper() for sql, _ in conn.calls]
    assert "DELETE" in kinds
    assert "INSERT" in kinds
    assert kinds.index("DELETE") < kinds.index("INSERT")  # 먼저 지우고 넣음

    del_sql, del_params = next(
        (s, prm) for s, prm in conn.calls if s.strip().upper().startswith("DELETE"))
    low = del_sql.lower()
    assert "review_issue" in low
    assert "github_pr_number" in low      # 그 PR 것만 지움
    assert "agent" in low                 # 그 agent 것만
    assert "performance" in del_params
    assert 42 in del_params
