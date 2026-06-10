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


# ─── F1: top-1 인용 + 짧은 요약 (SESSION F1 §2-B) ────────────────────────────

def test_format_context_top_1_only():
    """docs가 여러 개여도 첫 번째 문서(top-1)만 인용 — 두 번째 이후 제목 없음."""
    from rag.augment import format_context
    docs = [
        {"doc_title": "가이드 A", "source_url": "", "content": "A 내용"},
        {"doc_title": "가이드 B", "source_url": "", "content": "B 내용"},
        {"doc_title": "가이드 C", "source_url": "", "content": "C 내용"},
    ]
    out = format_context(docs)
    assert "가이드 A" in out
    assert "가이드 B" not in out
    assert "가이드 C" not in out


def test_format_context_summary_truncated_to_120_chars():
    """content가 길면 요약(첫 문장/핵심) 120자 이하로 잘린다."""
    from rag.augment import format_context
    long_content = "가" * 200  # 200자 내용
    docs = [{"doc_title": "가이드", "source_url": "", "content": long_content}]
    out = format_context(docs)
    # 📖 제목 줄을 제외한 나머지 요약 부분이 120자 이하
    summary_part = "\n".join(
        ln for ln in out.splitlines() if not ln.startswith("📖")
    ).strip()
    assert len(summary_part) <= 120


def test_format_context_first_sentence_only():
    """여러 문장 content에서 첫 문장만 인용한다 — 두 번째 문장 이후 없음."""
    from rag.augment import format_context
    multi = "첫 번째 문장입니다. 두 번째 문장입니다. 세 번째 문장입니다."
    docs = [{"doc_title": "가이드", "source_url": "", "content": multi}]
    out = format_context(docs)
    assert "첫 번째 문장" in out
    assert "두 번째 문장" not in out


def test_format_context_summary_skips_markdown_heading():
    """content 첫 줄이 마크다운 제목(#…)이면 요약은 그 줄을 건너뛰고 첫 산문을 쓴다.

    제목은 📖 줄이 이미 보여주므로 같은 제목을 두 번 인용하지 않는다(실 코멘트에서
    '📖 제목\\n## 제목' 중복 출력 재현 → 방지).
    """
    from rag.augment import format_context
    content = ("## 테스트 커버리지 가이드 — TEST-001\n\n"
               "새 코드는 커버리지 80% 이상을 유지한다. 자세한 규칙은 아래.")
    docs = [{"doc_title": "테스트 커버리지 가이드 — TEST-001",
             "source_url": "", "content": content}]
    out = format_context(docs)
    assert "커버리지 80%" in out                      # 산문 요약이 들어간다
    assert "##" not in out                            # 마크다운 제목 기호 그대로 안 나옴
    assert out.count("테스트 커버리지 가이드") == 1   # 제목 중복 없음


def test_format_context_summary_skips_yaml_frontmatter():
    """content가 YAML 머리말(--- … ---)로 시작하면 요약은 머리말을 건너뛰고 첫 산문을 쓴다.

    실측: KMS로 올린 가이드 청크가 '--- policy_key: …' 로 시작 → 요약줄에 기술
    메타데이터가 노출됨 → 건너뛰기 방어.
    """
    from rag.augment import format_context
    content = ("---\npolicy_key: complexity\nrule_id: PERF-001\n---\n\n"
               "## 시간복잡도 가이드\n\n중첩 루프는 3단 이상이면 Major. 자세한 건 아래.")
    docs = [{"doc_title": "시간복잡도 가이드", "source_url": "", "content": content}]
    out = format_context(docs)
    assert "중첩 루프" in out                  # 산문 요약이 들어간다
    assert "policy_key" not in out             # 머리말 키가 노출되지 않음
    assert "---" not in out


def test_format_context_single_line_no_trailing_newline():
    """단일 문서 인용 결과에 불필요한 빈 줄/개행이 없다."""
    from rag.augment import format_context
    docs = [{"doc_title": "규칙", "source_url": "http://wiki/r", "content": "selectinload 사용 권장"}]
    out = format_context(docs)
    assert not out.endswith("\n")
    # 빈 줄(연속 개행) 없음
    assert "\n\n" not in out
