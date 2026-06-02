"""Dev4 요청 §3.5 — Issue 3컬럼(keyword/sub_keyword/metric_value) TDD 테스트.

- keyword     : 대분류 (고정 한글 라벨, GROUP BY 통계 키)
- sub_keyword : 세부 대상 (함수명·위치 등)
- metric_value: 수치 (있을 때만, 없으면 빈 문자열)

각 탐지기가 §3.5 표대로 채우는지 검증.
"""
import textwrap
from pathlib import Path

from contracts import Issue

SAMPLE_REPO = Path(__file__).parent / "fixtures" / "sample_repo"


# ─── 헬퍼 ────────────────────────────────────────────────────────────────────
def _write(tmp_path, code: str) -> tuple[str, dict]:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "f.py").write_text(textwrap.dedent(code), encoding="utf-8")
    return str(tmp_path), {"src/f.py": set(range(1, 100))}


# ─── 0) 모델 기본값 ───────────────────────────────────────────────────────────
def test_issue_new_fields_default_empty():
    """Issue의 새 3필드는 기본 빈 문자열 (기존 호출 호환)."""
    i = Issue(severity="Minor", file="x.py", message="m", rule_id="R")
    assert i.keyword == ""
    assert i.sub_keyword == ""
    assert i.metric_value == ""


# ─── 1) TEST-001 커버리지 ─────────────────────────────────────────────────────
def test_coverage_keyword_fields():
    """TEST-001 → keyword='커버리지 미충족', sub_keyword='(전체)', metric_value='20.0%'."""
    from test_verification.coverage import measure
    issues, _ = measure(str(SAMPLE_REPO))
    assert len(issues) == 1
    i = issues[0]
    assert i.keyword == "커버리지 미충족"
    assert i.sub_keyword == "(전체)"
    assert i.metric_value == "20.0%"


# ─── 2) TEST-004 테스트 누락 ──────────────────────────────────────────────────
def test_missing_funcs_keyword_fields():
    """TEST-004 → keyword='테스트 누락', sub_keyword=함수명(메시지와 일치), metric_value=''."""
    from test_verification.missing_funcs import detect
    issues = detect(str(SAMPLE_REPO), {"src/posts.py": set(range(1, 100))})
    assert issues, "TEST-004 이슈가 하나 이상 나와야 함"
    for i in issues:
        assert i.keyword == "테스트 누락"
        assert i.sub_keyword, "함수명이 비어 있으면 안 됨"
        assert f"'{i.sub_keyword}'" in i.message  # 메시지의 함수명과 동일
        assert i.metric_value == ""


# ─── 3) PERF-002 N+1 ──────────────────────────────────────────────────────────
def test_nplus1_keyword_fields(tmp_path):
    """PERF-002 → keyword='N+1 쿼리', sub_keyword='파일:줄', metric_value=''."""
    from performance.nplus1 import detect
    repo, changed = _write(tmp_path, """
        for item in items:
            db.query(item)
    """)
    issues = detect(repo, changed)
    assert len(issues) == 1
    i = issues[0]
    assert i.keyword == "N+1 쿼리"
    assert i.sub_keyword == f"src/f.py:{i.line}"
    assert i.metric_value == ""


# ─── 4) PERF-001 복잡도 ───────────────────────────────────────────────────────
def test_complexity_keyword_fields(tmp_path):
    """PERF-001 → keyword='시간복잡도', sub_keyword='O(n^2)', metric_value=''."""
    from performance.complexity import detect
    repo, changed = _write(tmp_path, """
        for x in xs:
            for y in ys:
                z = x + y
    """)
    issues = detect(repo, changed)
    assert len(issues) == 1
    i = issues[0]
    assert i.keyword == "시간복잡도"
    assert i.sub_keyword == "O(n^2)"
    assert i.metric_value == ""


# ─── 5) TEST-003 엣지케이스 (휴리스틱) ────────────────────────────────────────
def test_edge_cases_keyword_fields(tmp_path, monkeypatch):
    """TEST-003 → keyword='엣지케이스 누락', sub_keyword=함수명, metric_value=''."""
    from test_verification import edge_cases
    monkeypatch.setattr(edge_cases, "_has_llm_key", lambda: False)
    repo, changed = _write(tmp_path, """
        def calc_price(price, rate):
            return price * (1 - rate)
    """)
    issues = edge_cases.detect(repo, changed)
    assert len(issues) == 1
    i = issues[0]
    assert i.keyword == "엣지케이스 누락"
    assert i.sub_keyword == "calc_price"
    assert i.metric_value == ""


# ─── 6) PERF-003 메모리 누수 (휴리스틱) ───────────────────────────────────────
def test_memory_leak_keyword_fields(tmp_path, monkeypatch):
    """PERF-003 → keyword='메모리 누수', sub_keyword='파일:줄', metric_value=''."""
    from performance import memory_leak
    monkeypatch.setattr(memory_leak, "_has_llm_key", lambda: False)
    repo, changed = _write(tmp_path, """
        EVENTS = []

        def log_event(evt):
            EVENTS.append(evt)
    """)
    issues = memory_leak.detect(repo, changed)
    assert len(issues) == 1
    i = issues[0]
    assert i.keyword == "메모리 누수"
    assert i.sub_keyword == f"src/f.py:{i.line}"
    assert i.metric_value == ""


# ─── 7) 로컬 SQLite persist 라운드트립 ─────────────────────────────────────────
def test_persist_sqlite_roundtrips_keyword_columns(tmp_path):
    """persist() → scan_issues에 keyword/sub_keyword/metric_value 저장·복원."""
    import sqlite3

    import persist as p
    from contracts import AgentOutput, SummaryCount

    issue = Issue(
        severity="Major", file="(전체)", line=None, message="커버리지 낮음",
        rule_id="TEST-001", keyword="커버리지 미충족", sub_keyword="(전체)",
        metric_value="26.7%",
    )
    out = AgentOutput(
        task_id="t", scan_id=1, pr_id="P", agent="test_verification",
        issues=[issue], summary=SummaryCount(major=1),
    )

    db = str(tmp_path / "d.db")
    orig = p.DB_PATH
    p.DB_PATH = db
    try:
        p.persist(1, [out])
    finally:
        p.DB_PATH = orig

    conn = sqlite3.connect(db)
    conn.executescript(p.SCHEMA)
    row = conn.execute(
        "SELECT keyword, sub_keyword, metric_value FROM scan_issues WHERE scan_id=1"
    ).fetchone()
    conn.close()
    assert row == ("커버리지 미충족", "(전체)", "26.7%")
