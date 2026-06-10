"""Task 13 — persist.py TDD 테스트.

단위 테스트: SQLite (in-memory / temp DB)
통합 테스트: GCP Postgres 트랜잭션 + 롤백 (POSTGRES_URL 필요, psycopg2 필요)
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import uuid

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contracts import AgentOutput, Issue, SummaryCount


# ─── 픽스처 헬퍼 ────────────────────────────────────────────────────────────────

def _make_outputs(scan_id: int = 1) -> list[AgentOutput]:
    """5 issues (3 test_verification + 2 performance) + 2 summaries."""
    tv_issues = [
        Issue(severity="Major", file="(전체)", line=None, message="커버리지 낮음", rule_id="TEST-001"),
        Issue(severity="Minor", file="src/posts.py", line=4, message="테스트 없음", rule_id="TEST-004"),
        Issue(severity="Minor", file="src/posts.py", line=16, message="테스트 없음2", rule_id="TEST-004"),
    ]
    perf_issues = [
        Issue(severity="Major", file="src/posts.py", line=7, message="N+1 쿼리", rule_id="PERF-002"),
        Issue(severity="Minor", file="src/posts.py", line=16, message="O(n^2)", rule_id="PERF-001"),
    ]
    out_tv = AgentOutput(
        task_id="demo-task-1", scan_id=scan_id, pr_id="PR-1",
        agent="test_verification", issues=tv_issues,
        summary=SummaryCount(major=1, minor=2),
        metrics={"coverage_line": 0.20}, execution_ms=100,
    )
    out_perf = AgentOutput(
        task_id="demo-task-1", scan_id=scan_id, pr_id="PR-1",
        agent="performance", issues=perf_issues,
        summary=SummaryCount(major=1, minor=1),
        metrics=None, execution_ms=100,
    )
    return [out_tv, out_perf]


# ─── 단위 테스트 (SQLite) ────────────────────────────────────────────────────────

class TestPersistSQLite:
    """persist() 함수 — 로컬 SQLite 경로를 임시 파일로 격리해 테스트."""

    def setup_method(self):
        self._tf = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._db_path = self._tf.name
        self._tf.close()

    def teardown_method(self):
        try:
            os.unlink(self._db_path)
        except OSError:
            pass

    def _persist(self, scan_id, outputs):
        import persist as p
        orig = p.DB_PATH
        p.DB_PATH = self._db_path
        try:
            p.persist(scan_id, outputs)
        finally:
            p.DB_PATH = orig

    def _readback(self, scan_id):
        from persist import SCHEMA
        conn = sqlite3.connect(self._db_path)
        conn.executescript(SCHEMA)
        issues = conn.execute(
            "SELECT agent,severity,rule_id,file,line FROM scan_issues "
            "WHERE scan_id=? ORDER BY agent,id", (scan_id,)
        ).fetchall()
        summaries = conn.execute(
            "SELECT agent,critical,major,minor,metrics FROM scan_summaries "
            "WHERE scan_id=? ORDER BY agent", (scan_id,)
        ).fetchall()
        conn.close()
        return issues, summaries

    def test_persist_creates_scan_issues(self):
        """5개 이슈가 scan_issues에 INSERT된다."""
        outputs = _make_outputs(scan_id=1)
        self._persist(1, outputs)
        issues, _ = self._readback(1)
        assert len(issues) == 5

    def test_persist_creates_scan_summaries(self):
        """2개 agent의 집계가 scan_summaries에 생성된다."""
        outputs = _make_outputs(scan_id=1)
        self._persist(1, outputs)
        _, summaries = self._readback(1)
        assert len(summaries) == 2

    def test_persist_summary_counts_match(self):
        """test_verification summary: major=1, minor=2 / performance: major=1, minor=1"""
        outputs = _make_outputs(scan_id=1)
        self._persist(1, outputs)
        _, summaries = self._readback(1)
        by_agent = {r[0]: r for r in summaries}
        tv = by_agent["test_verification"]
        assert tv[1] == 0  # critical
        assert tv[2] == 1  # major
        assert tv[3] == 2  # minor
        perf = by_agent["performance"]
        assert perf[2] == 1  # major
        assert perf[3] == 1  # minor

    def test_persist_roundtrips_dev2_aligned_columns(self):
        """Dev2 통일 신규 5컬럼이 scan_issues에 저장·복원된다."""
        issue = Issue(
            severity="Major", file="src/cart.py", line=8, message="N+1",
            rule_id="PERF-002",
            github_id="kskt1234",
            code_snippet="def load(uid):\n    return db.query(uid)",
            programming_language="python",
            framework="django",
            framework_version="4.2.1",
        )
        out = AgentOutput(
            task_id="t", scan_id=7, pr_id="P", agent="performance",
            issues=[issue], summary=SummaryCount(major=1),
        )
        self._persist(7, [out])
        from persist import SCHEMA
        conn = sqlite3.connect(self._db_path)
        conn.executescript(SCHEMA)
        row = conn.execute(
            "SELECT github_id, code_snippet, programming_language, framework, "
            "framework_version FROM scan_issues WHERE scan_id=7"
        ).fetchone()
        conn.close()
        assert row == ("kskt1234", "def load(uid):\n    return db.query(uid)",
                       "python", "django", "4.2.1")

    def test_persist_metrics_stored_as_json(self):
        """test_verification metrics가 JSON 텍스트로 저장된다."""
        outputs = _make_outputs(scan_id=1)
        self._persist(1, outputs)
        _, summaries = self._readback(1)
        by_agent = {r[0]: r for r in summaries}
        raw = by_agent["test_verification"][4]
        assert raw is not None
        parsed = json.loads(raw)
        assert abs(parsed["coverage_line"] - 0.20) < 0.001

    def test_persist_performance_metrics_none(self):
        """performance metrics는 NULL."""
        outputs = _make_outputs(scan_id=1)
        self._persist(1, outputs)
        _, summaries = self._readback(1)
        by_agent = {r[0]: r for r in summaries}
        assert by_agent["performance"][4] is None

    def test_persist_idempotent_rerun(self):
        """같은 scan_id+agent로 두 번 persist해도 이슈가 중복되지 않는다 (DELETE+INSERT 멱등성)."""
        outputs = _make_outputs(scan_id=2)
        self._persist(2, outputs)
        self._persist(2, outputs)  # 재실행
        issues, summaries = self._readback(2)
        assert len(issues) == 5   # 중복 없음
        assert len(summaries) == 2

    def test_persist_empty_issues(self):
        """이슈 없는 AgentOutput도 summary 행은 생성된다."""
        out = AgentOutput(
            task_id="t", scan_id=3, pr_id="P",
            agent="performance", issues=[],
            summary=SummaryCount(), metrics=None, execution_ms=0,
        )
        self._persist(3, [out])
        issues, summaries = self._readback(3)
        assert len(issues) == 0
        assert len(summaries) == 1


# ─── _pg_url() placeholder 감지 ────────────────────────────────────────────────

def test_pg_url_ignores_placeholder_env(monkeypatch):
    """루트 .env의 placeholder POSTGRES_URL은 무시하고 형제 .env가 없으면 None.

    컨테이너가 루트 .env placeholder로 뜰 때 실 GCP 대신 None 반환해야 함.
    형제 .env도 없는 격리 환경으로 테스트.
    """
    import persist as p
    monkeypatch.setenv("POSTGRES_URL", "postgresql://user:password@host:5432/dbname")
    # 형제 .env가 없는 것처럼 — os.path.exists가 False 반환
    monkeypatch.setattr(p.os.path, "exists", lambda path: False)
    result = p._pg_url()
    assert result is None  # placeholder → None (실 URL 아님)


def test_is_placeholder_url():
    """_is_placeholder_url: placeholder 패턴 감지."""
    import persist as p
    assert p._is_placeholder_url("postgresql://user:password@host:5432/dbname") is True
    assert p._is_placeholder_url("postgresql://postgres:secret@34.22.101.111:5432/tasklink") is False
    assert p._is_placeholder_url("") is False


def test_pg_url_accepts_real_url(monkeypatch):
    """실 GCP URL(IP 포함)은 그대로 반환해야 한다."""
    import persist as p
    real = "postgresql://postgres:secret%21@34.22.101.111:5432/tasklink"
    monkeypatch.setenv("POSTGRES_URL", real)
    assert p._pg_url() == real


def test_pg_url_empty_env_falls_back_to_dotenv(monkeypatch, tmp_path):
    """POSTGRES_URL env가 없으면 형제 .env에서 읽어야 한다."""
    import persist as p
    monkeypatch.delenv("POSTGRES_URL", raising=False)
    fake_env = tmp_path / ".env"
    real = "postgresql://postgres:x@1.2.3.4:5432/db"
    fake_env.write_text(f"POSTGRES_URL={real}\n", encoding="utf-8")
    # .env 경로 반환을 fake_env 경로로 치환
    import unittest.mock as mock
    orig_join = os.path.join
    with mock.patch.object(p.os.path, "join", side_effect=lambda *a: str(fake_env) if a and a[-1] == ".env" else orig_join(*a)):
        result = p._pg_url()
    assert result == real


# ─── 통합 테스트 (GCP Postgres, 트랜잭션+롤백) ───────────────────────────────────

psycopg2 = pytest.importorskip("psycopg2", reason="psycopg2 미설치 — 통합 테스트 스킵")


def _pg_url():
    import persist as _p
    url = os.getenv("POSTGRES_URL")
    if url and not _p._is_placeholder_url(url):
        return url
    env = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(env):
        for line in open(env, encoding="utf-8"):
            line = line.strip()
            if line.startswith("POSTGRES_URL="):
                val = line.split("=", 1)[1]
                if not _p._is_placeholder_url(val):
                    return val
    return None


@pytest.fixture(scope="module")
def pg_conn():
    url = _pg_url()
    if not url:
        pytest.skip("POSTGRES_URL 없음 — GCP 통합 테스트 스킵")
    import psycopg2 as pg2
    conn = pg2.connect(url, connect_timeout=10)
    yield conn
    conn.rollback()
    conn.close()


class TestPersistPGIntegration:
    """GCP Postgres — 완전 롤백으로 공유 DB 변경 0 보장."""

    def test_persist_pg_five_issues_two_summaries(self, pg_conn):
        """persist_pg → scan_issues 5행 + scan_summaries 2행 확인, 롤백으로 흔적 0."""
        from persist import persist_pg

        outputs = _make_outputs(scan_id=0)  # scan_id는 아래서 대체
        uid = str(uuid.uuid4())

        with pg_conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users(user_id, name) VALUES(%s, %s)",
                (uid, "dev3_test_persist (rollback)"),
            )
            cur.execute(
                "INSERT INTO scan_executions(task_id, pr_id, user_id) "
                "VALUES(%s, %s, %s) RETURNING id",
                ("task-persist-test", "PR-persist-test", uid),
            )
            scan_id = cur.fetchone()[0]

        # AgentOutput의 scan_id를 실제 발급된 값으로 교체
        real_outputs = _make_outputs(scan_id=scan_id)

        persist_pg(scan_id, real_outputs, conn=pg_conn)

        with pg_conn.cursor() as cur:
            cur.execute(
                "SELECT agent,severity,rule_id FROM scan_issues "
                "WHERE scan_id=%s ORDER BY agent,id",
                (scan_id,),
            )
            issues = cur.fetchall()
            cur.execute(
                "SELECT agent,critical,major,minor,metrics FROM scan_summaries "
                "WHERE scan_id=%s ORDER BY agent",
                (scan_id,),
            )
            summaries = cur.fetchall()

        pg_conn.rollback()  # 공유 DB 변경 0

        # 검증
        assert len(issues) == 5, f"scan_issues 5행 기대, 실제 {len(issues)}행"
        assert len(summaries) == 2, f"scan_summaries 2행 기대, 실제 {len(summaries)}행"
        agents_in_issues = {r[0] for r in issues}
        assert agents_in_issues == {"test_verification", "performance"}
        agents_in_summaries = {r[0] for r in summaries}
        assert agents_in_summaries == {"test_verification", "performance"}

    def test_persist_pg_summary_values(self, pg_conn):
        """persist_pg → summary critical/major/minor + metrics 값 정확성."""
        from persist import persist_pg

        uid = str(uuid.uuid4())
        with pg_conn.cursor() as cur:
            cur.execute("INSERT INTO users(user_id, name) VALUES(%s,%s)",
                        (uid, "dev3_test_summary (rollback)"))
            cur.execute(
                "INSERT INTO scan_executions(task_id, pr_id, user_id) "
                "VALUES(%s,%s,%s) RETURNING id",
                ("task-summary-test", "PR-summary-test", uid),
            )
            scan_id = cur.fetchone()[0]

        real_outputs = _make_outputs(scan_id=scan_id)
        persist_pg(scan_id, real_outputs, conn=pg_conn)

        with pg_conn.cursor() as cur:
            cur.execute(
                "SELECT agent,critical,major,minor,metrics FROM scan_summaries "
                "WHERE scan_id=%s ORDER BY agent",
                (scan_id,),
            )
            rows = cur.fetchall()

        pg_conn.rollback()

        by_agent = {r[0]: r for r in rows}
        tv = by_agent["test_verification"]
        assert tv[1] == 0 and tv[2] == 1 and tv[3] == 2  # critical/major/minor
        assert tv[4] is not None  # metrics jsonb
        assert by_agent["performance"][4] is None  # performance metrics = NULL
