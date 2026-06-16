"""Dev4 요청 — Issue.sub_category(표준 세부 유형 라벨) TDD 테스트.

sub_category: 우리가 실제 탐지하는 것만 고정 라벨 (rule_id 1:1 매핑, LLM 없음).
  - PERF-001 복잡도   → "Nested Loop"
  - PERF-002 N+1      → "Database/API Loop Call"
  - TEST-003 엣지케이스 → "null·빈값 미처리"
  - TEST-001 커버리지  → "라인·브랜치"

안 잡는 8개는 만들지 않음(백로그). 우리가 탐지하는 나머지 2개도 라벨 부여:
  - PERF-003 메모리 누수 → "Unbounded Collection Growth"
  - TEST-004 테스트 누락 → "Untested Public Function"
"""
import textwrap
from pathlib import Path

from contracts import Issue

SAMPLE_REPO = Path(__file__).parent / "fixtures" / "sample_repo"


def _write(tmp_path, code: str) -> tuple[str, dict]:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "f.py").write_text(textwrap.dedent(code), encoding="utf-8")
    return str(tmp_path), {"src/f.py": set(range(1, 100))}


# ─── 0) 모델 기본값 ───────────────────────────────────────────────────────────
def test_issue_sub_category_default_empty():
    """Issue.sub_category 기본 빈 문자열 (기존 호출 호환)."""
    i = Issue(severity="Minor", file="x.py", message="m", rule_id="R")
    assert i.sub_category == ""


# ─── 1) PERF-001 복잡도 → Nested Loop ─────────────────────────────────────────
def test_complexity_sub_category(tmp_path):
    from performance.complexity import detect
    repo, changed = _write(tmp_path, """
        for x in xs:
            for y in ys:
                z = x + y
    """)
    issues = detect(repo, changed)
    assert len(issues) == 1
    assert issues[0].sub_category == "Nested Loop"


# ─── 2) PERF-002 N+1 → Database/API Loop Call ─────────────────────────────────
def test_nplus1_sub_category(tmp_path):
    from performance.nplus1 import detect
    repo, changed = _write(tmp_path, """
        for item in items:
            db.query(item)
    """)
    issues = detect(repo, changed)
    assert len(issues) == 1
    assert issues[0].sub_category == "Database/API Loop Call"


# ─── 3) TEST-003 엣지케이스 → null·빈값 미처리 ────────────────────────────────
def test_edge_cases_sub_category(tmp_path, monkeypatch):
    from test_verification import edge_cases
    monkeypatch.setattr(edge_cases, "_has_llm_key", lambda: False)
    repo, changed = _write(tmp_path, """
        def calc_price(price, rate):
            return price * (1 - rate)
    """)
    issues = edge_cases.detect(repo, changed)
    assert len(issues) == 1
    assert issues[0].sub_category == "null·빈값 미처리"


# ─── 4) TEST-001 커버리지 → 라인·브랜치 ───────────────────────────────────────
def test_coverage_sub_category():
    from test_verification.coverage import measure
    issues, _ = measure(str(SAMPLE_REPO))
    assert len(issues) == 1
    assert issues[0].sub_category == "라인·브랜치"


# ─── 5) PERF-003 메모리 누수 → Unbounded Collection Growth ────────────────────
def test_memory_leak_sub_category(tmp_path, monkeypatch):
    from performance import memory_leak
    monkeypatch.setattr(memory_leak, "_has_llm_key", lambda: False)
    repo, changed = _write(tmp_path, """
        EVENTS = []

        def log_event(evt):
            EVENTS.append(evt)
    """)
    issues = memory_leak.detect(repo, changed)
    assert len(issues) == 1
    assert issues[0].sub_category == "Unbounded Collection Growth"


# ─── 6) TEST-004 테스트 누락 → Untested Public Function ───────────────────────
def test_missing_funcs_sub_category():
    from test_verification.missing_funcs import detect
    issues = detect(str(SAMPLE_REPO), {"src/posts.py": set(range(1, 100))})
    assert issues, "TEST-004 이슈가 하나 이상 나와야 함"
    for i in issues:
        assert i.sub_category == "Untested Public Function"


# ─── 7) 로컬 SQLite persist 라운드트립 ─────────────────────────────────────────
def test_persist_sqlite_roundtrips_sub_category(tmp_path):
    """persist() → scan_issues에 sub_category 저장·복원."""
    import sqlite3

    import persist as p
    from contracts import AgentOutput, SummaryCount

    issue = Issue(
        severity="Major", file="src/cart.py", line=8, message="N+1",
        rule_id="PERF-002", keyword="N+1 쿼리",
        sub_category="Database/API Loop Call",
    )
    out = AgentOutput(
        task_id="t", scan_id=2, pr_id="P", agent="performance",
        issues=[issue], summary=SummaryCount(major=1),
    )

    db = str(tmp_path / "d.db")
    orig = p.DB_PATH
    p.DB_PATH = db
    try:
        p.persist(2, [out])
    finally:
        p.DB_PATH = orig

    conn = sqlite3.connect(db)
    conn.executescript(p.SCHEMA)
    row = conn.execute(
        "SELECT sub_category FROM scan_issues WHERE scan_id=2"
    ).fetchone()
    conn.close()
    assert row == ("Database/API Loop Call",)
