"""Dev4 요청 — Issue.code_context(함수 한 줄 설명) TDD 테스트.

흐름: 이슈가 가리키는 함수 소스를 추출(AST=사실) → LLM이 한 줄 설명(판단) →
issue.code_context에 채움. 출력 계약(AgentOutput)은 불변, 선택 필드만 채움.

- GOOGLE_API_KEY 없으면 비활성(dormant): code_context는 빈 문자열로 남음.
- 같은 함수의 여러 이슈는 LLM 1회만 호출(캐시).
- 테스트에서는 describe를 주입(mock)하거나 _has_llm_key를 monkeypatch.
"""
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from contracts import (AgentOutput, Developer, Dev3Input, Issue, RepoInfo,
                       SummaryCount)

SAMPLE_REPO = Path(__file__).parent / "fixtures" / "sample_repo"


def _write(tmp_path, code: str) -> str:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "f.py").write_text(textwrap.dedent(code), encoding="utf-8")
    return str(tmp_path)


# ─── 0) 모델 기본값 ───────────────────────────────────────────────────────────
def test_issue_code_context_default_empty():
    """Issue.code_context 기본 빈 문자열 (기존 호출 호환)."""
    i = Issue(severity="Minor", file="x.py", message="m", rule_id="R")
    assert i.code_context == ""


# ─── 1) 키 없으면 describe_function은 빈 문자열 (안전) ─────────────────────────
def test_describe_function_empty_without_key(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    from enrich.code_context import describe_function
    assert describe_function("def f(): pass") == ""


# ─── 2) 키 없으면 augment는 비활성(이슈 그대로) ───────────────────────────────
def test_augment_dormant_without_key(tmp_path, monkeypatch):
    from enrich import code_context
    monkeypatch.setattr(code_context, "_has_llm_key", lambda: False)
    repo = _write(tmp_path, """
        def load_cart_items(uid):
            return db.query(uid)
    """)
    issue = Issue(severity="Minor", file="src/f.py", line=2,
                  message="m", rule_id="PERF-002")
    code_context.augment_issues([issue], repo,
                                describe=lambda s: "호출되면 안 됨")
    assert issue.code_context == ""


# ─── 3) 키 있으면 함수 설명을 code_context에 채움 ─────────────────────────────
def test_augment_sets_code_context(tmp_path, monkeypatch):
    from enrich import code_context
    monkeypatch.setattr(code_context, "_has_llm_key", lambda: True)
    repo = _write(tmp_path, """
        def load_cart_items(uid):
            for x in items:
                db.query(x)
    """)
    issue = Issue(severity="Major", file="src/f.py", line=3,
                  message="N+1", rule_id="PERF-002")
    code_context.augment_issues(
        [issue], repo, describe=lambda s: "장바구니 항목 불러오는 함수")
    assert issue.code_context == "장바구니 항목 불러오는 함수"


# ─── 4) line=None 이슈(커버리지 전체)는 건너뜀 ────────────────────────────────
def test_augment_skips_issue_without_line(tmp_path, monkeypatch):
    from enrich import code_context
    monkeypatch.setattr(code_context, "_has_llm_key", lambda: True)
    repo = _write(tmp_path, "def f(): pass\n")
    issue = Issue(severity="Major", file="(전체)", line=None,
                  message="cov", rule_id="TEST-001")
    code_context.augment_issues([issue], repo, describe=lambda s: "X")
    assert issue.code_context == ""


# ─── 5) 같은 함수의 두 이슈 → LLM 1회만 호출(캐시) ───────────────────────────
def test_augment_caches_same_function(tmp_path, monkeypatch):
    from enrich import code_context
    monkeypatch.setattr(code_context, "_has_llm_key", lambda: True)
    repo = _write(tmp_path, """
        def busy(items):
            for x in items:
                db.query(x)
            for a in items:
                for b in items:
                    pass
    """)
    calls = {"n": 0}

    def fake(src):
        calls["n"] += 1
        return "바쁜 함수"

    i1 = Issue(severity="Major", file="src/f.py", line=3,
               message="N+1", rule_id="PERF-002")
    i2 = Issue(severity="Minor", file="src/f.py", line=6,
               message="O(n^2)", rule_id="PERF-001")
    code_context.augment_issues([i1, i2], repo, describe=fake)
    assert i1.code_context == "바쁜 함수"
    assert i2.code_context == "바쁜 함수"
    assert calls["n"] == 1  # 같은 함수 → 1회만


# ─── 6) 모듈 레벨(함수 밖) 줄은 함수 못 찾음 → 빈 문자열 ──────────────────────
def test_augment_module_level_line_no_function(tmp_path, monkeypatch):
    from enrich import code_context
    monkeypatch.setattr(code_context, "_has_llm_key", lambda: True)
    repo = _write(tmp_path, "X = 1\nY = 2\n")
    issue = Issue(severity="Minor", file="src/f.py", line=1,
                  message="m", rule_id="PERF-001")
    code_context.augment_issues([issue], repo, describe=lambda s: "X")
    assert issue.code_context == ""


# ─── 7) main.run() 끝까지 연결 (mock describe) ────────────────────────────────
def test_main_run_populates_code_context(monkeypatch):
    from enrich import code_context
    from main import run
    monkeypatch.setattr(code_context, "_has_llm_key", lambda: True)
    monkeypatch.setattr(code_context, "describe_function", lambda s: "설명됨")

    diff = (SAMPLE_REPO.parent / "sample_pr.diff").read_text(encoding="utf-8")
    inp = Dev3Input(
        task_id="t", scan_id=1, pr_id="P", pr_diff=diff,
        repo=RepoInfo(clone_url="", commit_sha=""), developer=Developer(id="d"),
    )
    outputs = run(inp, str(SAMPLE_REPO))
    all_issues = [i for o in outputs for i in o.issues]
    enriched = [i for i in all_issues if i.code_context == "설명됨"]
    assert enriched, "함수 안 이슈는 code_context가 채워져야 함"


# ─── 7b) code_snippet: 함수 전체 소스 (AST=사실, 키 없이도 채움) ──────────────
def test_code_snippet_filled_without_key(tmp_path, monkeypatch):
    from enrich import code_context
    monkeypatch.setattr(code_context, "_has_llm_key", lambda: False)
    repo = _write(tmp_path, """
        def load_cart_items(uid):
            for x in items:
                db.query(x)
    """)
    issue = Issue(severity="Major", file="src/f.py", line=3,
                  message="N+1", rule_id="PERF-002")
    code_context.augment_issues([issue], repo, describe=lambda s: "안 불림")
    # 함수 전체 소스가 code_snippet에 그대로 (LLM 키 불필요)
    assert "def load_cart_items(uid):" in issue.code_snippet
    assert "db.query(x)" in issue.code_snippet
    # LLM 설명(code_context)은 키 없으니 빈 값
    assert issue.code_context == ""


# ─── 7c) main.run: code_context(LLM설명)은 성능(PERF) 이슈에만, code_snippet·name_of_function은 함수 단위 이슈 모두 ─────────
def test_main_run_enriches_perf_only(monkeypatch):
    from enrich import code_context
    from main import run
    monkeypatch.setattr(code_context, "_has_llm_key", lambda: True)
    monkeypatch.setattr(code_context, "describe_function", lambda s: "설명됨")

    diff = (SAMPLE_REPO.parent / "sample_pr.diff").read_text(encoding="utf-8")
    inp = Dev3Input(
        task_id="t", scan_id=1, pr_id="P", pr_diff=diff,
        repo=RepoInfo(clone_url="", commit_sha=""), developer=Developer(id="d"),
    )
    outputs = run(inp, str(SAMPLE_REPO))

    # test_verification 이슈: code_context = LLM 설명 아닌 결정적 라벨(sub_category/keyword)
    # LLM 설명("설명됨")은 절대 test 이슈에 들어가면 안 됨
    for o in outputs:
        if o.agent == "test_verification":
            for i in o.issues:
                assert i.code_context != "설명됨", f"TEST 이슈엔 LLM 설명이 들어가면 안 됨: {i.rule_id}"

    # performance 이슈 중 함수 안에 있는 건 code_snippet·code_context 둘 다 채워짐
    perf_issues = [i for o in outputs if o.agent == "performance" for i in o.issues]
    assert any(i.code_snippet for i in perf_issues), "PERF 함수 이슈엔 code_snippet"
    assert any(i.code_context == "설명됨" for i in perf_issues), "PERF 함수 이슈엔 code_context"


# ─── 7d) main.run: test 이슈의 name_of_function·code_snippet (함수 가리키는 경우) ──
def test_main_run_test_issues_get_function_name(monkeypatch):
    """TEST-004(테스트 누락)처럼 특정 함수 줄을 가리키는 test 이슈는
    name_of_function·code_snippet이 채워져야 한다.
    TEST-001(커버리지)처럼 line=None인 이슈는 빈값 유지(정직).
    """
    from enrich import code_context
    from main import run
    monkeypatch.setattr(code_context, "_has_llm_key", lambda: False)  # code_context(LLM)는 안 씀

    diff = (SAMPLE_REPO.parent / "sample_pr.diff").read_text(encoding="utf-8")
    inp = Dev3Input(
        task_id="t", scan_id=1, pr_id="P", pr_diff=diff,
        repo=RepoInfo(clone_url="", commit_sha=""), developer=Developer(id="d"),
    )
    outputs = run(inp, str(SAMPLE_REPO))

    tv_issues = [i for o in outputs if o.agent == "test_verification" for i in o.issues]
    assert tv_issues, "test_verification 이슈가 있어야 함"

    # line=None(TEST-001 커버리지)은 빈값 — 정직
    no_line = [i for i in tv_issues if i.line is None]
    for i in no_line:
        assert i.name_of_function == "", f"line=None 이슈는 name_of_function 빈값: {i.rule_id}"
        assert i.code_snippet == "", f"line=None 이슈는 code_snippet 빈값: {i.rule_id}"

    # line 있는 이슈(TEST-004 등)는 함수 가리키면 name_of_function 채워짐
    with_line = [i for i in tv_issues if i.line is not None]
    if with_line:
        # 함수 안을 가리키는 이슈가 있으면 적어도 하나는 name_of_function이 채워져야 함
        fn_filled = [i for i in with_line if i.name_of_function]
        assert fn_filled, "함수 가리키는 TEST 이슈엔 name_of_function이 채워져야 함"


# ─── (D) code_context = 결정적 라벨 (sub_category → keyword 우선순위) ─────────────
def test_code_context_label_uses_sub_category_first(tmp_path, monkeypatch):
    """sub_category가 있으면 code_context에 그대로 채움 (LLM 없이, 항상 결정적)."""
    from enrich import code_context
    monkeypatch.setattr(code_context, "_has_llm_key", lambda: False)
    repo = _write(tmp_path, """
        def load_cart(uid):
            for x in items:
                db.query(x)
    """)
    issue = Issue(severity="Major", file="src/f.py", line=3,
                  message="N+1", rule_id="PERF-002",
                  sub_category="N+1 쿼리", keyword="성능")
    code_context.augment_issues([issue], repo)
    assert issue.code_context == "N+1 쿼리"  # sub_category 우선


def test_code_context_label_falls_back_to_keyword(tmp_path, monkeypatch):
    """sub_category 없으면 keyword로 폴백."""
    from enrich import code_context
    monkeypatch.setattr(code_context, "_has_llm_key", lambda: False)
    repo = _write(tmp_path, """
        def check_auth(req):
            user = db.query(req.id)
            return user
    """)
    issue = Issue(severity="Major", file="src/f.py", line=3,
                  message="쿼리 문제", rule_id="PERF-002",
                  sub_category="", keyword="authentication")
    code_context.augment_issues([issue], repo)
    assert issue.code_context == "authentication"  # sub_category 없으니 keyword


def test_code_context_label_empty_when_no_sub_or_keyword(tmp_path, monkeypatch):
    """sub_category도 keyword도 없으면 code_context 빈값(가짜 금지)."""
    from enrich import code_context
    monkeypatch.setattr(code_context, "_has_llm_key", lambda: False)
    repo = _write(tmp_path, """
        def compute(x):
            return x * 2
    """)
    issue = Issue(severity="Minor", file="src/f.py", line=2,
                  message="복잡도", rule_id="PERF-001",
                  sub_category="", keyword="")
    code_context.augment_issues([issue], repo)
    assert issue.code_context == ""  # 둘 다 없으면 빈값(정직)


def test_code_context_label_not_overwritten_by_llm_key(tmp_path, monkeypatch):
    """LLM 키가 있어도 perf 이슈가 아닌 경우(with_llm=False) 결정적 라벨 사용."""
    from enrich import code_context
    monkeypatch.setattr(code_context, "_has_llm_key", lambda: True)
    repo = _write(tmp_path, """
        def missing_test(uid):
            return db.query(uid)
    """)
    issue = Issue(severity="Minor", file="src/f.py", line=2,
                  message="테스트 없음", rule_id="TEST-004",
                  sub_category="함수 테스트 누락", keyword="coverage")
    code_context.augment_issues([issue], repo, with_llm=False)
    assert issue.code_context == "함수 테스트 누락"  # with_llm=False → 결정적 라벨


def test_llm_failure_falls_back_to_label(tmp_path, monkeypatch):
    """LLM 호출 실패(빈 문자열) 시 code_context를 비워두지 않고 결정적 라벨로 폴백.

    실측: 유료 키 크레딧 소진(429)이면 perf 행 code_context가 ∅로 적재됨 →
    라벨(sub_category/keyword)로라도 채운다. LLM 복구 시 자동으로 설명이 우선.
    """
    from enrich import code_context
    monkeypatch.setattr(code_context, "_has_llm_key", lambda: True)
    repo = _write(tmp_path, """
        def load_cart(uid):
            for x in items:
                db.query(x)
    """)
    issue = Issue(severity="Major", file="src/f.py", line=3,
                  message="N+1", rule_id="PERF-002",
                  sub_category="", keyword="N+1 쿼리")
    code_context.augment_issues([issue], repo, describe=lambda s: "")  # LLM 실패 모사
    assert issue.code_context == "N+1 쿼리"  # 빈값 대신 라벨 폴백


# ─── 8) 로컬 SQLite persist 라운드트립 ─────────────────────────────────────────
def test_persist_sqlite_roundtrips_code_context(tmp_path):
    import sqlite3

    import persist as p

    issue = Issue(
        severity="Major", file="src/cart.py", line=8, message="N+1",
        rule_id="PERF-002", code_context="장바구니 항목 불러오는 함수",
    )
    out = AgentOutput(
        task_id="t", scan_id=3, pr_id="P", agent="performance",
        issues=[issue], summary=SummaryCount(major=1),
    )
    db = str(tmp_path / "d.db")
    orig = p.DB_PATH
    p.DB_PATH = db
    try:
        p.persist(3, [out])
    finally:
        p.DB_PATH = orig

    conn = sqlite3.connect(db)
    conn.executescript(p.SCHEMA)
    row = conn.execute(
        "SELECT code_context FROM scan_issues WHERE scan_id=3"
    ).fetchone()
    conn.close()
    assert row == ("장바구니 항목 불러오는 함수",)


# ─── 9) describe_function — 신 SDK(google.genai) 세임 (8-0a) ──────────────────
def test_describe_function_uses_new_sdk_client(monkeypatch):
    """describe_function이 genai.Client(api_key=...) 신 SDK를 호출한다."""
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key-code")
    mock_resp = MagicMock()
    mock_resp.text = '{"description": "장바구니 항목을 불러오는 함수"}'
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_resp

    with patch("google.genai.Client", return_value=mock_client) as MockClient:
        from enrich.code_context import describe_function
        result = describe_function("def load_cart(uid): pass")

    MockClient.assert_called_once_with(api_key="test-key-code")
    mock_client.models.generate_content.assert_called_once()
    assert result == "장바구니 항목을 불러오는 함수"
