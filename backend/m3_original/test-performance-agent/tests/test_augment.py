"""R7 — rag/augment.py TDD 테스트 (RAG 설계서 §5ⓑ, §6 미들웨어).

검색결과(docs) → 코멘트용 rag_context 문자열 포맷. 정성 가이드만.
augment_issues: 각 이슈 message로 검색 → issue.rag_context 채움 (retriever 주입 가능).
DB·LLM 불필요 — 순수 포맷 + 주입된 가짜 검색으로 고립 테스트.
"""
from contracts import Issue


# ─── 포맷터 ───────────────────────────────────────────────────────────────────
def test_format_context_includes_title_url_content():
    from rag.augment import format_context
    docs = [{"doc_title": "ORM 가이드", "source_url": "http://wiki/orm",
             "content": "우리 팀은 selectinload 표준"}]
    out = format_context(docs)
    assert "ORM 가이드" in out
    assert "http://wiki/orm" in out
    assert "selectinload" in out


def test_format_context_empty_docs_returns_empty():
    from rag.augment import format_context
    assert format_context([]) == ""


def test_format_context_no_url_no_markdown_link():
    from rag.augment import format_context
    out = format_context([{"doc_title": "가이드", "content": "내용"}])
    assert "가이드" in out
    assert "](" not in out  # url 없으면 마크다운 링크 형식 안 씀


# ─── 미들웨어 (retriever 주입) ────────────────────────────────────────────────
def test_augment_issues_fills_rag_context():
    from rag.augment import augment_issues
    issue = Issue(severity="Major", file="src/x.py", line=7,
                  message="N+1 쿼리 발생", rule_id="PERF-002")

    def fake_search(query):
        assert query == "N+1 쿼리 발생"   # 위험 4: message 통째로
        return [{"doc_title": "ORM 가이드", "source_url": "http://wiki/orm",
                 "content": "selectinload 표준"}]

    augment_issues([issue], search=fake_search)
    assert "selectinload" in issue.rag_context
    assert "http://wiki/orm" in issue.rag_context


def test_augment_issues_no_docs_leaves_empty_context():
    from rag.augment import augment_issues
    issue = Issue(severity="Minor", file="src/x.py", line=1,
                  message="무관한 이슈", rule_id="TEST-004")
    augment_issues([issue], search=lambda q: [])
    assert issue.rag_context == ""
