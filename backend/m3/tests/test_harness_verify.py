"""eval.harness 환각 자동검증(string-match) 단위 테스트 — LLM 호출 없음 (브리프 §4.2).

검증 계약 (contracts/README.md):
- Finding.rule_id 는 코퍼스에 실존해야 한다.
- Finding.rule_quote 는 해당 규칙 문서(§청크 원천)에 string-match 되어야 한다.
- Finding.evidence_lines 의 각 줄은 diff 에 string-match 되어야 한다.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from contracts import Finding
from eval.harness import build_corpus_index, verify_finding

RULE_API = """# [CONV-API-001] async 함수 내 동기 HTTP 금지
- severity: Major
- 배경(사고 이력): 2025-11 이벤트루프 블로킹 사고

## §1 규칙
async 함수 안에서 동기 requests 호출을 금지한다. 반드시 httpx.AsyncClient 를 사용한다.

## §4 예외 조항
scripts/ 와 batch/ 하위 일회성 배치 코드는 적용 제외.
"""

RULE_LOG = """# [CONV-LOG-003] print 로깅 금지
- severity: Major
- 배경(사고 이력): 2024-12 PII 평문 로그 유출

## §1 규칙
print() 로깅을 금지한다. struct_logger.log(event=...) 만 사용한다.
"""

DIFF = """diff --git a/app/api.py b/app/api.py
--- a/app/api.py
+++ b/app/api.py
@@ -1,4 +1,6 @@
 async def fetch_user(uid):
-    return cache.get(uid)
+    resp = requests.get(f"https://api.internal/users/{uid}")
+    return resp.json()
"""


@pytest.fixture()
def corpus_dir(tmp_path: Path) -> Path:
    d = tmp_path / "corpus"
    d.mkdir()
    (d / "external_api.md").write_text(RULE_API, encoding="utf-8")
    (d / "logging.md").write_text(RULE_LOG, encoding="utf-8")
    (d / "README.md").write_text("# corpus 안내문 — 규칙 문서 아님", encoding="utf-8")
    return d


def make_finding(**kw) -> Finding:
    base = dict(
        rule_id="CONV-API-001",
        verdict="violation",
        severity="Major",
        rule_quote="동기 requests 호출을 금지한다",
        file="app/api.py",
        evidence_lines=['+    resp = requests.get(f"https://api.internal/users/{uid}")'],
        reasoning="조항-코드 대조 요약",
    )
    base.update(kw)
    return Finding(**base)


def test_corpus_index_parses_rule_docs(corpus_dir):
    idx = build_corpus_index(corpus_dir)
    # README.md 는 rule_id 헤더가 없으므로 제외된다
    assert set(idx) == {"CONV-API-001", "CONV-LOG-003"}
    assert "§1" in idx["CONV-API-001"].sections
    assert "httpx.AsyncClient" in idx["CONV-API-001"].text


def test_verify_valid_citation_passes(corpus_dir):
    idx = build_corpus_index(corpus_dir)
    v = verify_finding(make_finding(), DIFF, idx)
    assert v["ok"]
    assert v["rule_id_ok"] and v["quote_ok"] and v["evidence_ok"]
    assert v["reasons"] == []


def test_verify_unknown_rule_id_fails(corpus_dir):
    idx = build_corpus_index(corpus_dir)
    v = verify_finding(make_finding(rule_id="CONV-API-999"), DIFF, idx)
    assert not v["ok"] and not v["rule_id_ok"]
    assert any("rule_id" in r for r in v["reasons"])


def test_verify_fabricated_quote_fails(corpus_dir):
    idx = build_corpus_index(corpus_dir)
    v = verify_finding(
        make_finding(rule_quote="모든 HTTP 호출은 재시도 3회를 구현해야 한다"), DIFF, idx
    )
    assert not v["ok"] and not v["quote_ok"]


def test_verify_quote_whitespace_normalized(corpus_dir):
    # LLM이 공백을 한 칸으로 줄여 옮겨도 환각이 아니다 (공백 정규화 후 일치)
    idx = build_corpus_index(corpus_dir)
    v = verify_finding(
        make_finding(rule_quote="반드시  httpx.AsyncClient  를 사용한다"), DIFF, idx
    )
    assert v["quote_ok"]


def test_verify_quote_from_other_rule_doc_fails(corpus_dir):
    # rule_id 가 실존해도 인용문이 '해당' 규칙 문서에 없으면 환각이다
    idx = build_corpus_index(corpus_dir)
    v = verify_finding(
        make_finding(rule_quote="struct_logger.log(event=...) 만 사용한다"), DIFF, idx
    )
    assert not v["quote_ok"]


def test_verify_empty_quote_fails(corpus_dir):
    idx = build_corpus_index(corpus_dir)
    v = verify_finding(make_finding(rule_quote="  "), DIFF, idx)
    assert not v["quote_ok"]


def test_verify_evidence_without_diff_marker_passes(corpus_dir):
    # judge 가 +/- 마커 없이 코드 줄만 옮겨도 diff 부분일치로 인정
    idx = build_corpus_index(corpus_dir)
    v = verify_finding(
        make_finding(
            evidence_lines=['resp = requests.get(f"https://api.internal/users/{uid}")']
        ),
        DIFF,
        idx,
    )
    assert v["evidence_ok"]


def test_verify_evidence_not_in_diff_fails(corpus_dir):
    idx = build_corpus_index(corpus_dir)
    v = verify_finding(
        make_finding(evidence_lines=["resp = urllib.request.urlopen(url)"]), DIFF, idx
    )
    assert not v["ok"] and not v["evidence_ok"]
    assert any("evidence" in r for r in v["reasons"])
