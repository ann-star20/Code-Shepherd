"""db_adapter 단위테스트 — mock SQLite 경로로 격리."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from contracts import Finding
from src.adapters.db_adapter import (
    _build_row,
    _code_snippet,
    _name_of_function,
    _mock_insert,
    _mock_conn,
    _KEYWORD_MAP,
    _RULE_MAP,
    _SEVERITY_MAP,
    _SUGGESTION_MAP,
    check_pg_connection,
    insert_review_issues,
)

_SCENE1_DIFF = """\
diff --git a/services/payment.py b/services/payment.py
index abc1234..def5678 100644
--- a/services/payment.py
+++ b/services/payment.py
@@ -1,8 +1,18 @@
+import asyncio
 import requests

-def get_payment(payment_id: str) -> dict:
-    return requests.get(f"https://api.pay.com/{payment_id}").json()
+class PaymentService:
+    async def verify_payment(self, payment_id: str) -> dict:
+        response = requests.get(
+            f"https://api.payment.com/v1/payments/{payment_id}",
+            timeout=10,
+        )
+        return response.json()
+
+    async def refund(self, payment_id: str, amount: int) -> dict:
+        result = requests.post(
+            "https://api.payment.com/v1/refunds",
+            json={"payment_id": payment_id, "amount": amount},
+        )
+        return result.json()
"""


def _make_finding(
    rule_id: str = "CONV-API-001",
    verdict: str = "violation",
    severity: str = "Major",
    evidence_lines: list[str] | None = None,
) -> Finding:
    return Finding(
        rule_id=rule_id,
        verdict=verdict,
        severity=severity,
        rule_quote="동기 requests 금지",
        file="src/api.py",
        evidence_lines=evidence_lines or ["+    r = requests.get(url)"],
        reasoning="이벤트루프 블로킹",
        fp_note=None,
    )


@pytest.fixture
def mock_db(tmp_path):
    """테스트마다 독립 SQLite DB."""
    return tmp_path / "test_review_issue.db"


# ── check_pg_connection ────────────────────────────────────────────────────────

def test_pg_connection_placeholder():
    saved_url = os.environ.pop("POSTGRES_URL", None)
    saved_host = os.environ.pop("DB_HOST", None)
    try:
        os.environ["POSTGRES_URL"] = "postgresql://user:password@host:5432/db"
        ok, msg = check_pg_connection()
        assert not ok
        assert "not configured" in msg.lower()
    finally:
        if saved_url:
            os.environ["POSTGRES_URL"] = saved_url
        if saved_host:
            os.environ["DB_HOST"] = saved_host


def test_pg_connection_not_set():
    saved_url = os.environ.pop("POSTGRES_URL", None)
    saved_host = os.environ.pop("DB_HOST", None)
    try:
        ok, msg = check_pg_connection()
        assert not ok
        assert "not configured" in msg.lower()
    finally:
        if saved_url:
            os.environ["POSTGRES_URL"] = saved_url
        if saved_host:
            os.environ["DB_HOST"] = saved_host


# ── _code_snippet ──────────────────────────────────────────────────────────────

def test_code_snippet_strips_plus():
    lines = ["+    r = requests.get(url)", "+    return r.json()"]
    result = _code_snippet(lines)
    assert result == "    r = requests.get(url)\n    return r.json()"
    assert "+" not in result


def test_code_snippet_strips_minus():
    lines = ["-    old = requests.get(url)"]
    assert _code_snippet(lines) == "    old = requests.get(url)"


def test_code_snippet_preserves_context_lines():
    lines = [" import requests", "+    r = requests.get(url)"]
    result = _code_snippet(lines)
    assert result.startswith(" import requests")


# ── _name_of_function ──────────────────────────────────────────────────────────

def test_name_from_evidence_def_line():
    """evidence_lines에 def 선언이 포함된 경우 — 함수명 직접 추출."""
    ev = [
        "+    async def verify_payment(self, payment_id: str) -> dict:",
        "+        response = requests.get(url)",
    ]
    assert _name_of_function(ev) == "verify_payment"


def test_name_from_diff_context():
    """evidence_lines에 def 없지만 diff 컨텍스트로 추출."""
    ev = [
        "+        response = requests.get(",
        '+            f"https://api.payment.com/v1/payments/{payment_id}",',
        "+            timeout=10,",
        "+        )",
    ]
    result = _name_of_function(ev, _SCENE1_DIFF)
    assert result == "verify_payment"


def test_name_from_diff_second_func():
    """diff 두 번째 함수(refund)의 evidence 라인에서 refund 추출."""
    ev = [
        '+        result = requests.post(',
        '+            "https://api.payment.com/v1/refunds",',
    ]
    result = _name_of_function(ev, _SCENE1_DIFF)
    assert result == "refund"


def test_name_returns_none_without_diff():
    """diff 없고 evidence에 def도 없으면 None."""
    ev = ["+    r = requests.get(url)"]
    assert _name_of_function(ev, "") is None


# ── _build_row ────────────────────────────────────────────────────────────────

def test_build_row_field_mapping():
    f = _make_finding("CONV-API-001")
    row = _build_row(f, pr_number=1, repository="owner/repo", github_id="testuser")

    assert row["agent"] == "dev3"
    assert row["severity"] == "medium"
    assert row["keyword"] == "동기 HTTP 호출"
    assert row["sub_category"] == "Async Sync HTTP Call - Event Loop Blocking"
    assert row["programming_language"] == "python"
    assert row["framework"] is None
    assert row["github_id"] == "testuser"
    assert "requests.get" in row["code_context"]


def test_build_row_code_snippet_no_prefix():
    """code_snippet은 +/- 접두 없는 순수 코드."""
    f = _make_finding(evidence_lines=["+    r = requests.get(url)"])
    row = _build_row(f, 1, "x/y", None)
    assert row["code_snippet"] == "    r = requests.get(url)"
    assert not row["code_snippet"].startswith("+")


def test_build_row_name_of_function_with_diff():
    """diff 전달 시 name_of_function 추출."""
    ev = [
        "+        response = requests.get(",
        '+            f"https://api.payment.com/v1/payments/{payment_id}",',
    ]
    f = _make_finding(evidence_lines=ev)
    row = _build_row(f, 1, "x/y", None, diff=_SCENE1_DIFF)
    assert row["name_of_function"] == "verify_payment"


def test_build_row_unknown_rule():
    f = _make_finding("CONV-UNKNOWN-099")
    row = _build_row(f, 1, "x/y", None)
    assert row["keyword"] == "CONV-UNKNOWN-099"
    assert row["sub_category"] == "CONV-UNKNOWN-099"


def test_build_row_severity_minor():
    f = _make_finding(severity="Minor")
    row = _build_row(f, 1, "x/y", None)
    assert row["severity"] == "low"


def test_build_row_suggestion_contains_rule_id():
    """suggestion 문구에 rule_id 출처가 포함되어 있다."""
    f = _make_finding("CONV-SQL-008")
    row = _build_row(f, 1, "x/y", None)
    assert "파라미터 바인딩" in row["suggestion"]
    assert "CONV-SQL-008" in row["suggestion"]


# ── _mock_insert + _mock_conn ─────────────────────────────────────────────────

def test_mock_insert_creates_row(mock_db):
    f = _make_finding()
    row = _build_row(f, 1, "owner/repo", "gh_user")
    _mock_insert(row, 1, "owner/repo", mock_db)

    conn = sqlite3.connect(str(mock_db))
    rows = conn.execute("SELECT agent, keyword, sub_category FROM review_issue").fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0] == ("dev3", "동기 HTTP 호출", "Async Sync HTTP Call - Event Loop Blocking")


def test_mock_insert_code_snippet_stored(mock_db):
    """code_snippet이 DB에 +/- 없이 저장된다."""
    f = _make_finding(evidence_lines=["+    r = requests.get(url)"])
    row = _build_row(f, 1, "owner/repo", None)
    _mock_insert(row, 1, "owner/repo", mock_db)

    conn = sqlite3.connect(str(mock_db))
    snippet = conn.execute("SELECT code_snippet FROM review_issue").fetchone()[0]
    conn.close()
    assert snippet == "    r = requests.get(url)"
    assert not snippet.startswith("+")


def test_mock_insert_multiple_findings(mock_db):
    findings = [
        _make_finding("CONV-API-001"),
        _make_finding("CONV-LOG-003"),
    ]
    for f in findings:
        row = _build_row(f, 1, "owner/repo", None)
        _mock_insert(row, 1, "owner/repo", mock_db)

    conn = sqlite3.connect(str(mock_db))
    count = conn.execute("SELECT count(*) FROM review_issue").fetchone()[0]
    conn.close()
    assert count == 2


# ── insert_review_issues 공개 API ─────────────────────────────────────────────

def test_insert_review_issues_disabled_by_default(mock_db, monkeypatch):
    monkeypatch.delenv("ENABLE_DB_WRITE", raising=False)
    findings = [_make_finding()]
    insert_review_issues(findings, 1, "owner/repo", _mock_db_path=mock_db)

    assert not mock_db.exists()


def test_insert_review_issues_enabled(mock_db, monkeypatch):
    monkeypatch.setenv("ENABLE_DB_WRITE", "true")
    monkeypatch.setenv("POSTGRES_URL", "postgresql://user:password@host:5432/db")
    monkeypatch.delenv("DB_HOST", raising=False)
    findings = [_make_finding("CONV-API-001"), _make_finding("CONV-LOG-003")]
    insert_review_issues(findings, 2, "owner/repo", github_id="alice", _mock_db_path=mock_db)

    conn = sqlite3.connect(str(mock_db))
    count = conn.execute("SELECT count(*) FROM review_issue").fetchone()[0]
    conn.close()
    assert count == 2


def test_insert_review_issues_passes_diff(mock_db, monkeypatch):
    """diff 파라미터가 _build_row까지 전달되어 name_of_function에 반영된다."""
    monkeypatch.setenv("ENABLE_DB_WRITE", "true")
    monkeypatch.delenv("DB_HOST", raising=False)
    monkeypatch.setenv("POSTGRES_URL", "postgresql://user:password@host:5432/db")

    ev = [
        "+        response = requests.get(",
        '+            f"https://api.payment.com/v1/payments/{payment_id}",',
    ]
    findings = [_make_finding(evidence_lines=ev)]
    insert_review_issues(findings, 1, "owner/repo", diff=_SCENE1_DIFF, _mock_db_path=mock_db)

    conn = sqlite3.connect(str(mock_db))
    name = conn.execute("SELECT name_of_function FROM review_issue").fetchone()[0]
    conn.close()
    assert name == "verify_payment"


def test_insert_review_issues_skips_no_violation(mock_db, monkeypatch):
    monkeypatch.setenv("ENABLE_DB_WRITE", "true")
    monkeypatch.setenv("POSTGRES_URL", "postgresql://user:password@host:5432/db")
    monkeypatch.delenv("DB_HOST", raising=False)
    findings = [
        _make_finding(verdict="violation"),
        _make_finding(verdict="no_violation"),
    ]
    insert_review_issues(findings, 3, "owner/repo", _mock_db_path=mock_db)

    conn = sqlite3.connect(str(mock_db))
    count = conn.execute("SELECT count(*) FROM review_issue").fetchone()[0]
    conn.close()
    assert count == 1


def test_insert_does_not_raise_on_db_error(mock_db, monkeypatch):
    monkeypatch.setenv("ENABLE_DB_WRITE", "true")
    monkeypatch.setenv("POSTGRES_URL", "postgresql://user:password@host:5432/db")
    monkeypatch.delenv("DB_HOST", raising=False)

    def bad_mock_insert(*_a, **_kw):
        raise RuntimeError("simulated DB error")

    monkeypatch.setattr("src.adapters.db_adapter._mock_insert", bad_mock_insert)
    findings = [_make_finding()]
    insert_review_issues(findings, 4, "owner/repo", _mock_db_path=mock_db)


# ── 맵 커버리지 ───────────────────────────────────────────────────────────────

def test_all_8_rules_in_keyword_map():
    expected = {
        "CONV-API-001", "CONV-TIME-002", "CONV-LOG-003", "CONV-DB-004",
        "CONV-DEP-005", "CONV-ERR-006", "CONV-CFG-007", "CONV-SQL-008",
    }
    assert expected == set(_KEYWORD_MAP.keys())


def test_all_8_rules_in_suggestion_map():
    assert set(_KEYWORD_MAP.keys()) == set(_SUGGESTION_MAP.keys())


def test_rule_map_format():
    """_RULE_MAP 값이 (keyword, sub_category) 튜플 형식 — 두 필드 모두 비어있지 않음."""
    for rule_id, (keyword, sub_cat) in _RULE_MAP.items():
        assert keyword, f"{rule_id}: keyword 비어있음"
        assert sub_cat, f"{rule_id}: sub_category 비어있음"
        # rule_id가 suggestion에 포함
        assert rule_id in _SUGGESTION_MAP.get(rule_id, ""), f"{rule_id}: suggestion에 rule_id 없음"
