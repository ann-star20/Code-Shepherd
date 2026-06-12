"""Policy as Data — 복잡도 기준이 DB(policy_store)에서 오고, 없으면 fallback.

판정 로직(complexity.py)은 그대로. 바뀌는 건 "기준값이 오는 곳"뿐. (커버리지와 동일 패턴)
"""
import textwrap

import pytest

from config import conventions, policy_store


@pytest.fixture(autouse=True)
def _reset_cache():
    policy_store.reset_cache()
    yield
    policy_store.reset_cache()


# ─── 1) DB 없으면 하드코딩 fallback 그대로 ────────────────────────────────────
def test_complexity_rules_fallback_without_db(monkeypatch):
    monkeypatch.setattr(policy_store, "get_params", lambda k: None)
    rules = conventions.complexity_rules()
    assert rules == conventions.COMPLEXITY_RULES
    assert rules["minor_depth"] == 2
    assert rules["major_depth"] == 3


# ─── 2) DB 정책이 있으면 그 값으로 (코드 수정 없이 기준 변경) ─────────────────
def test_complexity_rules_from_db(monkeypatch):
    db_rules = {"minor_depth": 1, "major_depth": 2}
    monkeypatch.setattr(policy_store, "get_params",
                        lambda k: db_rules if k == "complexity" else None)
    rules = conventions.complexity_rules()
    assert rules["minor_depth"] == 1
    assert rules["major_depth"] == 2


# ─── 3) DB params에 키가 빠지면 깨진 데이터 → fallback (안전) ─────────────────
def test_complexity_rules_ignores_invalid_db(monkeypatch):
    monkeypatch.setattr(policy_store, "get_params", lambda k: {"minor_depth": 1})
    rules = conventions.complexity_rules()
    assert rules == conventions.COMPLEXITY_RULES        # major_depth 없음 → fallback


# ─── 4) detect()가 DB 기준으로 판정 (end-to-end, DB는 mock) ───────────────────
def _write(tmp_path, code: str):
    src = tmp_path / "src"
    src.mkdir()
    (src / "f.py").write_text(textwrap.dedent(code), encoding="utf-8")
    return str(tmp_path), {"src/f.py": set(range(1, 100))}


def test_detect_uses_db_thresholds(tmp_path, monkeypatch):
    # DB에서 major_depth=2로 낮추면 2중 중첩 루프가 Major로 잡힘
    # (fallback이면 major_depth=3이라 2중은 Minor였을 것)
    db_rules = {"minor_depth": 1, "major_depth": 2}
    monkeypatch.setattr(policy_store, "get_params",
                        lambda k: db_rules if k == "complexity" else None)
    from performance.complexity import detect
    repo, changed = _write(tmp_path, """
        for x in xs:
            for y in ys:
                z = x + y
    """)
    issues = detect(repo, changed)
    assert len(issues) == 1
    assert issues[0].severity == "Major"        # DB 기준(major=2) → Major
    assert issues[0].rule_id == "PERF-001"


def test_detect_fallback_default(tmp_path, monkeypatch):
    # DB 없으면 fallback(minor=2, major=3) → 2중 중첩은 Minor
    monkeypatch.setattr(policy_store, "get_params", lambda k: None)
    from performance.complexity import detect
    repo, changed = _write(tmp_path, """
        for x in xs:
            for y in ys:
                z = x + y
    """)
    issues = detect(repo, changed)
    assert len(issues) == 1
    assert issues[0].severity == "Minor"        # fallback(major=3) → Minor
