"""Stage 3 청킹 단위 테스트.

순수 함수(_split_by_headers, _make_parent_chunks, _make_child_chunks)를
대상으로 경계값 및 코너 케이스를 검증한다.
"""

import pytest

from app.pipeline.stage3_chunk import (
    CHILD_MAX_TOKENS,
    CHILD_MIN_TOKENS,
    PARENT_MAX_TOKENS,
    PARENT_MIN_TOKENS,
    _make_child_chunks,
    _make_parent_chunks,
    _split_by_headers,
    stage3_chunk,
)


# ---------------------------------------------------------------------------
# _split_by_headers
# ---------------------------------------------------------------------------

def test_split_by_headers_with_pre_header_content():
    """첫 번째 헤더 이전 내용이 빈 헤더("")로 첫 섹션에 포함돼야 한다."""
    md = "문서 제목\n\n메타 정보\n\n## 섹션 1\n\n본문 내용"
    sections = _split_by_headers(md)
    assert sections[0][0] == ""  # 빈 헤더
    assert "문서 제목" in sections[0][1]  # pre-header 내용 보존
    assert sections[1][0] == "## 섹션 1"


def test_split_by_headers_no_headers():
    """헤더 없는 문서는 빈 헤더 하나의 단일 섹션으로 반환한다."""
    md = "그냥 본문입니다.\n\n두 번째 문단."
    sections = _split_by_headers(md)
    assert len(sections) == 1
    assert sections[0][0] == ""
    assert "그냥 본문" in sections[0][1]


def test_split_by_headers_empty_content_section_skipped():
    """내용 없는 헤더 섹션(H1 등)은 별도 섹션을 만들지 않는다 (H1은 pending 전달)."""
    md = "# 최상위 제목\n\n## 하위 섹션\n\n하위 내용"
    sections = _split_by_headers(md)
    # pre-header 없음, H1은 pending_h1으로 처리됨 → 직접 섹션 목록에 없을 수도 있음
    # H2 섹션은 반드시 포함
    header_texts = [s[0] for s in sections]
    assert "## 하위 섹션" in header_texts


# ---------------------------------------------------------------------------
# _make_parent_chunks
# ---------------------------------------------------------------------------

def test_make_parent_chunks_small_sections_merged():
    """작은 섹션들이 PARENT_MIN_TOKENS 이상이 될 때까지 병합돼야 한다."""
    # 아주 짧은 섹션 여러 개 → 하나의 parent로 병합
    sections = [
        ("## 섹션 A", "짧은 내용 A"),
        ("## 섹션 B", "짧은 내용 B"),
        ("## 섹션 C", "짧은 내용 C"),
    ]
    parents = _make_parent_chunks(sections, "doc-001")
    # 세 섹션 모두 짧으므로 적어도 하나의 parent에 병합됨
    assert len(parents) >= 1
    for p in parents:
        assert p["chunk_type"] == "parent"
        assert p["parent_chunk_id"] is None
        assert p["content"].strip()


def test_make_parent_chunks_oversized_section_split():
    """단일 섹션이 PARENT_MAX_TOKENS를 초과하면 강제 분할이 발생한다."""
    # 1만 자 텍스트 (1500토큰 초과 확실)
    long_content = "가 나 다 라 마 바 사 아 자 차 " * 600  # ~6000 tokens
    sections = [("## 큰 섹션", long_content)]
    parents = _make_parent_chunks(sections, "doc-002")
    assert len(parents) > 1  # 강제 분할로 여러 parent 생성
    for p in parents:
        assert p["token_count"] <= PARENT_MAX_TOKENS * 1.05  # 5% 여유


def test_make_parent_chunks_sets_chunk_index_not_set():
    """parent chunk에 chunk_index는 stage3_chunk에서 설정됨 — make_parent_chunks 자체는 설정 안 함."""
    sections = [("## 섹션", "내용")]
    parents = _make_parent_chunks(sections, "doc-003")
    # chunk_index 키가 없거나 None (stage3_chunk에서 부여)
    for p in parents:
        assert "chunk_index" not in p or p.get("chunk_index") is None


# ---------------------------------------------------------------------------
# _make_child_chunks
# ---------------------------------------------------------------------------

def test_make_child_chunks_links_to_parent():
    """child 청크의 parent_chunk_id가 parent의 chunk_id를 가리켜야 한다."""
    parent = {
        "chunk_id": "parent-uuid-1",
        "doc_id": "doc-004",
        "parent_chunk_id": None,
        "chunk_type": "parent",
        "content": "첫 문단.\n\n두 번째 문단.\n\n세 번째 문단.",
        "token_count": 30,
        "page_number": None,
        "section_header": "테스트 섹션",
    }
    children = _make_child_chunks(parent)
    for child in children:
        assert child["parent_chunk_id"] == "parent-uuid-1"
        assert child["chunk_type"] == "child"
        assert child["content"].strip()


def test_make_child_chunks_inherits_section_header():
    """child 청크는 parent의 section_header를 상속한다."""
    parent = {
        "chunk_id": "parent-uuid-2",
        "doc_id": "doc-005",
        "parent_chunk_id": None,
        "chunk_type": "parent",
        "content": "내용A.\n\n내용B.",
        "token_count": 20,
        "page_number": 3,
        "section_header": "상속 섹션",
    }
    children = _make_child_chunks(parent)
    for child in children:
        assert child["section_header"] == "상속 섹션"
        assert child["page_number"] == 3


# ---------------------------------------------------------------------------
# stage3_chunk (비동기 통합)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stage3_chunk_full_flow():
    """validated_markdown 입력 → parent + child 청크 생성 전체 흐름 검증."""
    md = """# 문서 제목

## 개요

이 문서는 KMS 파이프라인 테스트용 문서입니다.
개요 내용은 여기에 들어갑니다.

## 구현 세부사항

구현은 다음과 같이 진행됩니다.
Stage 3는 Markdown을 Parent-Child 계층으로 분할합니다.
청크 크기는 Parent 800-1500 토큰, Child 300-500 토큰입니다.
"""
    state = {
        "doc_id": "00000000-0000-0000-0000-000000000099",
        "validated_markdown": md,
        "status": "processing",
    }
    result = await stage3_chunk(state)

    chunks = result["chunks"]
    assert len(chunks) > 0

    parent_chunks = [c for c in chunks if c["chunk_type"] == "parent"]
    child_chunks = [c for c in chunks if c["chunk_type"] == "child"]

    assert len(parent_chunks) >= 1
    assert len(child_chunks) >= 1

    # child → parent 참조 정합성
    parent_ids = {c["chunk_id"] for c in parent_chunks}
    for child in child_chunks:
        assert child["parent_chunk_id"] in parent_ids

    # chunk_index 부여 확인
    for i, chunk in enumerate(chunks):
        assert chunk["chunk_index"] == i
