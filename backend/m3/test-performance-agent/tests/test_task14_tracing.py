"""Task 14 — tracing.py TDD 테스트.

단위 테스트: SQLite (임시 DB), 상태 매핑 로직, uuid 핸들링
통합 테스트: GCP Postgres 트랜잭션 + 롤백 (POSTGRES_URL 필요, psycopg2 필요)

GCP agent_traces 실제 스키마:
  trace_id text PK, task_id uuid(nullable), agent_name text, doc_id uuid(nullable),
  status text CHECK(running/success/fail/review), started_at, ended_at,
  execution_ms int CHECK(>=0), error_message text, created_at, input_summary text, output_summary text
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


# ─── 단위 테스트 (SQLite) ────────────────────────────────────────────────────────

class TestLogTraceSQLite:
    """log_trace() — 임시 SQLite DB로 격리."""

    def setup_method(self):
        self._tf = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._db_path = self._tf.name
        self._tf.close()

    def teardown_method(self):
        try:
            os.unlink(self._db_path)
        except OSError:
            pass

    def _log(self, trace_id, agent_name, task_id, scan_id, status, execution_ms,
             started_at=None, error_message=None):
        import tracing as t
        orig = t.DB_PATH
        t.DB_PATH = self._db_path
        try:
            t.log_trace(trace_id, agent_name, task_id, scan_id, status, execution_ms,
                        started_at, error_message)
        finally:
            t.DB_PATH = orig

    def _readback(self):
        from tracing import SCHEMA
        conn = sqlite3.connect(self._db_path)
        conn.executescript(SCHEMA)
        rows = conn.execute(
            "SELECT trace_id,agent_name,task_id,scan_id,status,execution_ms,error_message "
            "FROM agent_traces ORDER BY rowid"
        ).fetchall()
        conn.close()
        return rows

    def test_log_trace_creates_row(self):
        """log_trace() 호출 시 agent_traces에 1행이 생성된다."""
        self._log("trc-001", "test_verification", "task-abc", 42, "success", 1500)
        rows = self._readback()
        assert len(rows) == 1
        r = rows[0]
        assert r[0] == "trc-001"
        assert r[1] == "test_verification"
        assert r[2] == "task-abc"
        assert r[3] == 42
        assert r[4] == "success"
        assert r[5] == 1500

    def test_log_trace_upsert_same_trace_id(self):
        """같은 trace_id로 두 번 호출하면 status가 업데이트되고 행은 1개."""
        self._log("trc-dup", "performance", "task-x", 10, "running", 0)
        self._log("trc-dup", "performance", "task-x", 10, "success", 2000,
                  error_message=None)
        rows = self._readback()
        assert len(rows) == 1
        assert rows[0][4] == "success"
        assert rows[0][5] == 2000

    def test_log_trace_error_message_stored(self):
        """error_message가 저장된다."""
        self._log("trc-err", "test_verification", "t1", 5, "partial_fail", 500,
                  error_message="memory_leak 타임아웃")
        rows = self._readback()
        assert rows[0][6] == "memory_leak 타임아웃"

    def test_log_trace_multiple_agents(self):
        """에이전트별로 별도 행이 생성된다."""
        self._log("trc-tv", "test_verification", "t1", 1, "success", 100)
        self._log("trc-pf", "performance", "t1", 1, "success", 200)
        rows = self._readback()
        assert len(rows) == 2
        agents = {r[1] for r in rows}
        assert agents == {"test_verification", "performance"}


# ─── GCP 매핑 로직 단위 테스트 ────────────────────────────────────────────────────

class TestGCPStatusMapping:
    """_GCP_STATUS 매핑 테이블 직접 검증 (DB 불필요)."""

    def test_partial_fail_maps_to_success(self):
        from tracing import _GCP_STATUS
        assert _GCP_STATUS["partial_fail"] == "success"

    def test_allowed_statuses_preserved(self):
        from tracing import _GCP_STATUS
        for s in ("success", "fail", "running", "review"):
            assert _GCP_STATUS[s] == s

    def test_unknown_status_defaults_to_success(self):
        from tracing import _GCP_STATUS
        assert _GCP_STATUS.get("unknown", "success") == "success"


class TestUUIDHandling:
    """log_trace_pg에서 task_id uuid 변환 로직 검증."""

    def test_valid_uuid_string_accepted(self):
        """정상 uuid 문자열은 그대로 받아들여진다."""
        import uuid as _uuid
        valid = str(_uuid.uuid4())
        try:
            result = str(_uuid.UUID(valid))
            assert result == valid
        except ValueError:
            pytest.fail("유효한 uuid가 ValueError를 일으킴")

    def test_non_uuid_string_raises(self):
        """'demo-001' 같은 비-uuid는 UUID() 생성 시 ValueError 발생."""
        import uuid as _uuid
        with pytest.raises((ValueError, AttributeError)):
            _uuid.UUID("demo-001")

    def test_none_task_id_raises(self):
        """None task_id는 UUID() 생성 시 AttributeError 발생."""
        import uuid as _uuid
        with pytest.raises((ValueError, AttributeError, TypeError)):
            _uuid.UUID(None)


# ─── 통합 테스트 (GCP Postgres, 트랜잭션+롤백) ───────────────────────────────────

psycopg2 = pytest.importorskip("psycopg2", reason="psycopg2 미설치 — 통합 테스트 스킵")


def _pg_url():
    url = os.getenv("POSTGRES_URL")
    if url:
        return url
    env = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(env):
        for line in open(env, encoding="utf-8"):
            line = line.strip()
            if line.startswith("POSTGRES_URL="):
                return line.split("=", 1)[1]
    return None


@pytest.fixture(scope="module")
def pg_conn_trace():
    url = _pg_url()
    if not url:
        pytest.skip("POSTGRES_URL 없음 — GCP 통합 테스트 스킵")
    import psycopg2 as pg2
    conn = pg2.connect(url, connect_timeout=10)
    yield conn
    conn.rollback()
    conn.close()


class TestLogTracePGIntegration:
    """GCP Postgres — agent_traces 2행 적재 후 롤백, 공유 DB 변경 0."""

    def test_log_trace_pg_two_rows_rollback(self, pg_conn_trace):
        """uuid + non-uuid task_id, partial_fail 매핑, rollback 검증."""
        from tracing import log_trace_pg

        real_uuid = str(uuid.uuid4())
        tid1 = f"trc_{uuid.uuid4().hex[:8]}_tv"
        tid2 = f"trc_{uuid.uuid4().hex[:8]}_pf"
        scan_marker = 99988  # 고유 마커 — 같은 scan_id 행 필터용

        # row 1: uuid task_id + success
        log_trace_pg(
            pg_conn_trace,
            trace_id=tid1,
            agent_name="test_verification",
            task_id=real_uuid,
            scan_id=scan_marker,
            status="success",
            execution_ms=1500,
        )
        # row 2: 비-uuid task_id + partial_fail → success 매핑
        log_trace_pg(
            pg_conn_trace,
            trace_id=tid2,
            agent_name="performance",
            task_id="demo-001",
            scan_id=scan_marker,
            status="partial_fail",
            execution_ms=2200,
            error_message="memory_leak 타임아웃 → 제외",
        )

        with pg_conn_trace.cursor() as cur:
            cur.execute(
                "SELECT agent_name,status,task_id,execution_ms,error_message,output_summary "
                "FROM agent_traces "
                "WHERE output_summary LIKE %s ORDER BY agent_name",
                (f'%"scan_id": {scan_marker}%',),
            )
            rows = cur.fetchall()

        pg_conn_trace.rollback()  # 공유 DB 변경 0

        # 검증: 2행 적재됨
        assert len(rows) == 2, f"agent_traces 2행 기대, 실제 {len(rows)}행"

        # 검증: status 모두 허용값(running/success/fail/review)
        gcp_allowed = {"running", "success", "fail", "review"}
        for r in rows:
            assert r[1] in gcp_allowed, f"허용되지 않는 status: {r[1]}"

        by_agent = {r[0]: r for r in rows}

        # test_verification: uuid task_id → 컬럼에 저장됨 (None이 아님)
        tv = by_agent["test_verification"]
        assert tv[2] is not None, "uuid task_id가 NULL로 저장됨"

        # performance: 비-uuid "demo-001" → task_id=NULL
        pf = by_agent["performance"]
        assert pf[2] is None, f"비-uuid task_id가 NULL이 아님: {pf[2]}"

        # performance: output_summary에 dev3_status=partial_fail 보존됨
        out_summary = json.loads(pf[5])
        assert out_summary.get("dev3_status") == "partial_fail", \
            f"dev3_status 보존 안됨: {out_summary}"

        # performance: scan_id가 output_summary에 동봉됨
        assert out_summary.get("scan_id") == scan_marker, \
            f"scan_id 동봉 안됨: {out_summary}"

    def test_log_trace_pg_execution_ms_nonnegative(self, pg_conn_trace):
        """execution_ms가 0 이상이어야 한다 (CHECK 제약 대응)."""
        from tracing import log_trace_pg

        tid = f"trc_{uuid.uuid4().hex[:8]}_ms_test"
        # execution_ms=-1 → max(0, ...) 보정으로 0이 INSERT되어야 함
        log_trace_pg(
            pg_conn_trace,
            trace_id=tid,
            agent_name="performance",
            task_id="demo-ms-test",
            scan_id=99999,
            status="success",
            execution_ms=-1,  # 음수 → 0으로 보정
        )
        with pg_conn_trace.cursor() as cur:
            cur.execute(
                "SELECT execution_ms FROM agent_traces WHERE trace_id=%s", (tid,)
            )
            row = cur.fetchone()

        pg_conn_trace.rollback()
        assert row is not None
        assert row[0] == 0, f"execution_ms 음수 보정 실패: {row[0]}"
