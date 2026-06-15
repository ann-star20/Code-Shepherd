"""
TDD Cycle P4: Stage 3 child chunk size compliance 개선

문제:
  - child chunk 중 100~1500 토큰 범위 밖인 것이 약 7.4% 존재 (현재 92.6%)
  - 목표: compliance_rate ≥ 95%

원인:
  _make_child_chunks()에서 단락(paragraph) 분할 시 마지막 단락이 작으면
  100 토큰 미만의 child가 생성됨.

  예: 단락 A (490 tok) + 단락 B (60 tok) = 550 > CHILD_MAX_TOKENS(500)
  → child 1: 490 tok, child 2: 60 tok ← 비준수!

  추가 원인: 헤더 라인("## Section")이 단독 단락으로 분리되어 trailing 단락에
  붙지 못하고 버퍼가 작은 채로 flush됨.

해결 전략:
  _make_child_chunks() 반환 전, 100 토큰 미만 child를 인접 child와 병합하는
  _merge_small_children() 후처리 추가.

대상:
  - app.pipeline.stage3_chunk._make_child_chunks()
  - app.pipeline.stage3_chunk._merge_small_children()  [신규]
"""

import pytest
from unittest.mock import patch

from app.pipeline.stage3_chunk import (
    _make_child_chunks,
    stage3_chunk,
)

CHILD_COMPLIANCE_MIN = 100
CHILD_COMPLIANCE_MAX = 1500


def _make_parent(content: str, doc_id: str = "test_doc") -> dict:
    return {
        "chunk_id": "parent-001",
        "doc_id": doc_id,
        "parent_chunk_id": None,
        "chunk_type": "parent",
        "content": content,
        "token_count": 500,
        "page_number": None,
        "section_header": "테스트 섹션",
    }


# ────────────────────────────────────────────────────────────────
# Unit: _make_child_chunks() — compliance 검증
# ────────────────────────────────────────────────────────────────


class TestChildChunkCompliance:
    """child chunk 토큰 범위 준수 테스트."""

    def test_small_trailing_para_not_left_as_tiny_child(self):
        """
        P4 핵심 시나리오:
        490 tok 단락 + 60 tok 단락 → 550 > CHILD_MAX_TOKENS(500)으로 분리 시,
        60 tok child가 발생하면 안 됨 → 이전 child와 병합되어야 함.
        """
        call_seq = iter([490, 60])

        def mock_tokens(text: str) -> int:
            try:
                return next(call_seq)
            except StopIteration:
                return 10

        content = "대용량 단락 본문.\n\n작은 trailing 단락."
        parent = _make_parent(content)

        with patch("app.pipeline.stage3_chunk._count_tokens", side_effect=mock_tokens):
            children = _make_child_chunks(parent)

        token_counts = [c["token_count"] for c in children]
        assert all(t >= CHILD_COMPLIANCE_MIN for t in token_counts), (
            f"100 토큰 미만 child 발생: {token_counts}"
        )

    def test_two_tiny_paras_merged_into_one_child(self):
        """
        두 개의 매우 작은 단락(40 tok each)이 각각 child가 되지 않고
        하나의 합산 child로 병합되어야 함.
        """
        call_seq = iter([40, 40])

        def mock_tokens(text: str) -> int:
            try:
                return next(call_seq)
            except StopIteration:
                return 10

        content = "짧은 단락 A.\n\n짧은 단락 B."
        parent = _make_parent(content)

        with patch("app.pipeline.stage3_chunk._count_tokens", side_effect=mock_tokens):
            children = _make_child_chunks(parent)

        assert len(children) == 1, (
            f"작은 단락 2개가 병합되어 1개 child가 되어야 함: {len(children)}개 생성됨"
        )
        assert children[0]["token_count"] == 80

    def test_normal_sized_children_unchanged(self):
        """
        정상 크기(200~300 tok) child는 병합 없이 그대로 유지된다.
        """
        call_seq = iter([200, 250, 200])

        def mock_tokens(text: str) -> int:
            try:
                return next(call_seq)
            except StopIteration:
                return 10

        content = "단락 A.\n\n단락 B.\n\n단락 C."
        parent = _make_parent(content)

        with patch("app.pipeline.stage3_chunk._count_tokens", side_effect=mock_tokens):
            children = _make_child_chunks(parent)

        # 200+250=450 ≤ 500 → child1, 200 → child2
        assert len(children) == 2
        assert all(t >= CHILD_COMPLIANCE_MIN for t in [c["token_count"] for c in children])

    def test_single_para_child_below_compliance_still_returned(self):
        """
        단일 단락만 있는 경우: 이전 child가 없어 병합 불가.
        단독 child로 반환되되, 이 케이스는 parent 자체가 작은 경우.
        (이 경우는 parent 레벨 수정 범위이므로 child 레벨에서는 그대로 허용)
        """
        call_seq = iter([50])

        def mock_tokens(text: str) -> int:
            try:
                return next(call_seq)
            except StopIteration:
                return 10

        content = "짧은 단일 단락."
        parent = _make_parent(content)

        with patch("app.pipeline.stage3_chunk._count_tokens", side_effect=mock_tokens):
            children = _make_child_chunks(parent)

        # 단일 child: 병합 대상 없으므로 그대로 반환
        assert len(children) == 1

    def test_header_line_plus_content_not_split_as_tiny_header(self):
        """
        헤더 라인("## 섹션명")이 단독 단락으로 분리된 뒤
        trailing content와 합쳐질 때 tiny child가 생기지 않아야 함.
        """
        # 헤더(3 tok) + 큰 content(470 tok) + 또 다른 단락(60 tok)
        call_seq = iter([3, 470, 60])

        def mock_tokens(text: str) -> int:
            try:
                return next(call_seq)
            except StopIteration:
                return 10

        content = "## 섹션 제목\n\n긴 본문 내용.\n\ntrailing 단락."
        parent = _make_parent(content)

        with patch("app.pipeline.stage3_chunk._count_tokens", side_effect=mock_tokens):
            children = _make_child_chunks(parent)

        token_counts = [c["token_count"] for c in children]
        non_compliant = [t for t in token_counts if t < CHILD_COMPLIANCE_MIN]
        assert not non_compliant, (
            f"헤더+본문 분리 케이스에서 100 토큰 미만 child 발생: {token_counts}"
        )

    def test_all_children_below_compliance_max(self):
        """
        Child chunk는 CHILD_COMPLIANCE_MAX(1500 토큰)를 초과해서는 안 됨.
        단, parent 자체가 이미 ≤ 1500이므로 실질적으로 위반 불가.
        """
        call_seq = iter([400, 400, 300])

        def mock_tokens(text: str) -> int:
            try:
                return next(call_seq)
            except StopIteration:
                return 10

        content = "단락 A.\n\n단락 B.\n\n단락 C."
        parent = _make_parent(content)

        with patch("app.pipeline.stage3_chunk._count_tokens", side_effect=mock_tokens):
            children = _make_child_chunks(parent)

        for c in children:
            assert c["token_count"] <= CHILD_COMPLIANCE_MAX, (
                f"1500 토큰 초과 child 발생: {c['token_count']}"
            )

    def test_child_inherits_parent_metadata(self):
        """병합 후에도 doc_id, parent_chunk_id, chunk_type이 올바르게 유지된다."""
        call_seq = iter([490, 60])

        def mock_tokens(text: str) -> int:
            try:
                return next(call_seq)
            except StopIteration:
                return 10

        content = "긴 단락.\n\n짧은 단락."
        parent = _make_parent(content, doc_id="doc_abc")

        with patch("app.pipeline.stage3_chunk._count_tokens", side_effect=mock_tokens):
            children = _make_child_chunks(parent)

        for c in children:
            assert c["doc_id"] == "doc_abc"
            assert c["parent_chunk_id"] == "parent-001"
            assert c["chunk_type"] == "child"


# ────────────────────────────────────────────────────────────────
# Integration: stage3_chunk() 노드 통합 테스트
# ────────────────────────────────────────────────────────────────


class TestStage3ChunkIntegration:
    """stage3_chunk() LangGraph 노드 통합 테스트."""

    @pytest.mark.asyncio
    async def test_md03_like_short_doc_compliance(self):
        """
        md_03 시나리오: 짧은 섹션 여러 개를 가진 마크다운 문서.
        모든 child chunk가 100~1500 토큰 범위여야 함.
        """
        markdown = (
            "# 온보딩 가이드\n\n"
            "## 개요\n\n"
            "이 문서는 신입 직원을 위한 온보딩 가이드입니다. " * 20
            + "\n\n"
            "## 필수 준비 사항\n\n"
            "노트북 설정, 계정 생성, 사내 시스템 접근 권한을 신청합니다. " * 20
            + "\n\n"
            "## 첫 주 일정\n\n"
            "첫 주에는 팀 소개와 업무 환경 파악에 집중합니다. " * 15
            + "\n\n"
            "참고 사항: 궁금한 점은 HR에 문의하세요.\n"
        )
        state = {"doc_id": "md_03_test", "validated_markdown": markdown}
        result = await stage3_chunk(state)

        child_chunks = [c for c in result["chunks"] if c["chunk_type"] == "child"]
        assert child_chunks, "child chunk가 최소 1개 이상 생성되어야 함"

        non_compliant = [
            c for c in child_chunks
            if not (CHILD_COMPLIANCE_MIN <= c["token_count"] <= CHILD_COMPLIANCE_MAX)
        ]
        assert not non_compliant, (
            f"비준수 child chunks: "
            f"{[(c['token_count'], c['content'][:30]) for c in non_compliant]}"
        )

    @pytest.mark.asyncio
    async def test_pptx_like_slide_doc_compliance(self):
        """
        pptx_01 시나리오: 슬라이드 기반 짧은 섹션 문서.
        각 슬라이드가 독립 섹션으로 분리되어 작은 child가 생길 수 있음.
        """
        markdown = (
            "# 프로젝트 현황 보고\n\n"
            "## 슬라이드 1: 프로젝트 개요\n\n"
            "2024년 Q4 KMS 플랫폼 구축 프로젝트입니다. " * 15
            + "\n\n"
            "## 슬라이드 2: 진행 현황\n\n"
            "현재 Module 0~3 개발이 완료되었습니다. " * 15
            + "\n\n"
            "## 슬라이드 3: 다음 단계\n\n"
            "Module 4, 5 개발 및 통합 테스트를 진행합니다. " * 15
            + "\n\n"
            "## 슬라이드 4: 요약\n\n"
            "일정 내 완료 예정입니다.\n"
        )
        state = {"doc_id": "pptx_01_test", "validated_markdown": markdown}
        result = await stage3_chunk(state)

        child_chunks = [c for c in result["chunks"] if c["chunk_type"] == "child"]
        assert child_chunks, "child chunk가 최소 1개 이상 생성되어야 함"

        non_compliant = [
            c for c in child_chunks
            if not (CHILD_COMPLIANCE_MIN <= c["token_count"] <= CHILD_COMPLIANCE_MAX)
        ]
        assert not non_compliant, (
            f"비준수 child chunks: "
            f"{[(c['token_count'], c['content'][:30]) for c in non_compliant]}"
        )
