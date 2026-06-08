"""Policy as Data — config/policy_store.py TDD.

기준 숫자를 GCP convention_policies(jsonb)에서 읽는다. DB 못 읽으면 빈 dict 반환
→ 호출자가 하드코딩 fallback. 위험3: 숫자는 구조화 데이터로 정확히 읽음(LLM 아님).
모든 외부 의존(DB)은 monkeypatch로 고립.
"""
import pytest

from config import policy_store


@pytest.fixture(autouse=True)
def _reset_cache():
    policy_store.reset_cache()
    yield
    policy_store.reset_cache()


# ─── 1) DB 없음(POSTGRES_URL 미설정) → 빈 dict (fallback 유도) ─────────────────
def test_load_policies_empty_when_no_db(monkeypatch):
    monkeypatch.setattr(policy_store, "_connect", lambda: None)
    assert policy_store.load_policies() == {}
    assert policy_store.get_params("coverage") is None


# ─── 2) DB 예외 → 빈 dict (환각/장애 방지) ────────────────────────────────────
def test_load_policies_empty_on_exception(monkeypatch):
    def boom():
        raise RuntimeError("connection refused")
    monkeypatch.setattr(policy_store, "_connect", boom)
    assert policy_store.load_policies() == {}


# ─── 3) DB에 정책 있으면 그대로 읽음 (jsonb=dict) ─────────────────────────────
class _FakeCur:
    def __init__(self, rows):
        self._rows = rows
    def execute(self, *a):
        pass
    def fetchall(self):
        return self._rows
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows
        self.closed = False
    def cursor(self):
        return _FakeCur(self._rows)
    def close(self):
        self.closed = True


def test_load_policies_reads_db(monkeypatch):
    rows = [("coverage", {"default": 0.80, "payment": 0.90})]
    monkeypatch.setattr(policy_store, "_connect", lambda: _FakeConn(rows))
    params = policy_store.get_params("coverage")
    assert params == {"default": 0.80, "payment": 0.90}


# ─── 4) 캐시: 두 번째 호출은 DB 재조회 안 함 ──────────────────────────────────
def test_load_policies_cached(monkeypatch):
    calls = {"n": 0}

    def connect():
        calls["n"] += 1
        return _FakeConn([("coverage", {"default": 0.75})])
    monkeypatch.setattr(policy_store, "_connect", connect)
    policy_store.load_policies()
    policy_store.load_policies()
    assert calls["n"] == 1  # 캐시 → 1번만 연결


# ─── 5) upsert_policy: INSERT/ON CONFLICT SQL이 호출됨 ────────────────────────
def test_upsert_policy_executes(monkeypatch):
    captured = {}

    class Cur:
        def execute(self, sql, params=None):
            captured["sql"] = sql
            captured["params"] = params
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    class Conn:
        def cursor(self):
            return Cur()

    policy_store.upsert_policy(Conn(), "coverage", "TEST-001",
                              {"default": 0.80})
    assert "convention_policies" in captured["sql"]
    assert "ON CONFLICT" in captured["sql"]
    assert captured["params"][0] == "coverage"
    assert captured["params"][1] == "TEST-001"
