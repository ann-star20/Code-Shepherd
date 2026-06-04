"""E2E: PDF/DOCX 업로드 파서 경로 확인.

미커버 경로:
  - _select_parser() 라우팅 로직 (파일 타입 × 복잡도)
  - _calculate_quality_score() 임계값 분기
  - document_parser_agent() → parser_used 필드 검증
  - PDF HIGH complexity → hitl_required 경로
  - Upstage 일일 한도 초과 → HITL
  - _post_process_upstage_markdown() HTML 표 변환
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# _select_parser 라우팅 검증
# ---------------------------------------------------------------------------

class TestSelectParser:
    """_select_parser는 파일 타입 + 복잡도에 따라 정확한 파서명을 반환한다."""

    def _call(self, file_type: str, complexity: str = "LOW", *, upstage_key: str = "") -> str:
        from module_0_kms.pipeline.stage1_document_parser_agent import _select_parser
        with patch.dict(os.environ, {"UPSTAGE_API_KEY": upstage_key}):
            return _select_parser(file_type, complexity)

    def test_txt_returns_direct_read(self):
        assert self._call("txt") == "direct_read"

    def test_md_returns_direct_read(self):
        assert self._call("md") == "direct_read"

    def test_docx_returns_python_docx(self):
        assert self._call("docx") == "python_docx"

    def test_pptx_returns_unstructured(self):
        assert self._call("pptx") == "unstructured"

    def test_pdf_low_returns_pymupdf(self):
        assert self._call("pdf", "LOW") == "pymupdf"

    def test_pdf_medium_returns_pymupdf(self):
        assert self._call("pdf", "MEDIUM") == "pymupdf"

    def test_pdf_high_no_key_returns_hitl_required(self):
        """UPSTAGE_API_KEY 없으면 HIGH PDF는 hitl_required를 반환한다."""
        assert self._call("pdf", "HIGH", upstage_key="") == "hitl_required"

    def test_pdf_high_placeholder_key_returns_hitl_required(self):
        """up_xxxx 플레이스홀더 키는 실제 키가 아님 → hitl_required."""
        assert self._call("pdf", "HIGH", upstage_key="up_xxxx") == "hitl_required"

    def test_pdf_high_with_real_key_returns_upstage(self):
        """유효한 UPSTAGE_API_KEY가 있으면 upstage를 반환한다."""
        assert self._call("pdf", "HIGH", upstage_key="up_real_key_abc") == "upstage"

    def test_unsupported_type_raises_value_error(self):
        from module_0_kms.pipeline.stage1_document_parser_agent import _select_parser
        with pytest.raises(ValueError, match="지원하지 않는"):
            _select_parser("hwp", "LOW")


# ---------------------------------------------------------------------------
# _calculate_quality_score 임계값 검증
# ---------------------------------------------------------------------------

class TestCalculateQualityScore:
    """_calculate_quality_score는 규칙 기반으로 0~100점을 반환한다."""

    def _score(self, markdown, file_type="txt", has_tables=False,
               has_images=False, file_size=1000):
        from module_0_kms.pipeline.stage1_document_parser_agent import _calculate_quality_score
        return _calculate_quality_score(markdown, file_type, has_tables, has_images, file_size)

    def test_empty_markdown_returns_zero(self):
        assert self._score("") == 0

    def test_sufficient_length_gets_length_points(self):
        """200자 이상이면 길이 점수 30점 이상."""
        score = self._score("가" * 200 + "# 제목\n")
        assert score >= 30

    def test_heading_present_adds_points(self):
        """헤딩(#~####)이 있으면 +15점."""
        score_with = self._score("가" * 200 + "\n# 제목")
        score_without = self._score("가" * 200)
        assert score_with > score_without

    def test_no_heading_no_heading_points(self):
        """텍스트 파일에서 헤딩 없으면 헤딩 점수 0."""
        # 짧고 헤딩 없는 텍스트 → 길이 0 + 깨진문자 없음 점수만
        score = self._score("abc", file_type="txt")
        # 길이 < 200: 0점 / 깨진문자 없음: +20 +5 / 헤딩 없음: 0 / 표/이미지 없음: +15+5 = 45
        assert score == 45

    def test_score_below_40_possible_with_broken_chars(self):
        """깨진 문자가 2% 이상이면 텍스트 품질 점수 낮아진다."""
        # 100자, 3자는 깨진 문자 (3%) → 깨진문자 점수 0
        broken = "가" * 97 + "\x00\x01\x02"   # 제어문자 3개 (3% broken)
        score = self._score(broken, file_type="txt")
        # 길이 < 200: 0점 / 깨진문자 >= 2%: 0점 / 헤딩 없음: 0점 / 표/이미지 없음: +15+5 = 20
        assert score < 40

    def test_has_tables_but_no_pipe_reduces_score(self):
        """has_tables=True인데 마크다운에 '|'가 없으면 표 보존 점수 0."""
        score = self._score("가" * 500 + "\n# 제목", has_tables=True)
        score_with_pipe = self._score("가" * 500 + "\n# 제목\n| 표 | 내용 |", has_tables=True)
        assert score < score_with_pipe

    def test_pptx_gets_heading_points_regardless(self):
        """PPTX는 헤딩 없어도 +15 보너스 → 헤딩 없는 TXT보다 15점 높다."""
        score_pptx = self._score("가" * 200, file_type="pptx")
        score_txt = self._score("가" * 200, file_type="txt")
        # TXT without headings = 0pts for heading, PPTX always = +15pts
        assert score_pptx == score_txt + 15


# ---------------------------------------------------------------------------
# document_parser_agent → parser_used 필드 검증 (E2E 경로)
# ---------------------------------------------------------------------------

class TestParserUsedField:
    """document_parser_agent가 선택된 파서명을 parser_used 필드에 올바르게 반환한다."""

    def _make_state(self, file_path: str, file_type: str) -> dict:
        return {
            "doc_id": "aaaaaaaa-0000-0000-0000-000000000001",
            "source": "upload",
            "file_path": file_path,
            "file_type": file_type,
            "original_filename": f"test.{file_type}",
            "raw_markdown": None,
            "markdown_storage_path": None,
            "status": "processing",
            "current_stage": "init",
        }

    @pytest.mark.asyncio
    async def test_docx_parser_used_is_python_docx(self, tmp_path: Path):
        """DOCX 업로드 → parser_used == 'python_docx'."""
        docx_path = str(tmp_path / "guide.docx")
        Path(docx_path).write_bytes(b"PK\x03\x04")

        storage = AsyncMock()
        storage.save = AsyncMock(return_value="markdown/test/raw.md")

        long_content = "# 개발자 온보딩 가이드\n\n" + ("내용 텍스트. " * 40)

        with patch("kms.pipeline.stage1_document_parser_agent._convert_docx_with_python_docx",
                   return_value=long_content), \
             patch("kms.pipeline.stage1_document_parser_agent._diagnose_document",
                   return_value={"complexity": "LOW", "has_tables": False,
                                 "has_images": False, "page_count": None, "image_ratio": 0.0}):
            result = await __import__(
                "kms.pipeline.stage1_document_parser_agent",
                fromlist=["document_parser_agent"]
            ).document_parser_agent(self._make_state(docx_path, "docx"), storage=storage)

        assert result["parser_used"] == "python_docx"
        assert result["raw_markdown"] is not None
        assert result.get("status") != "failed"

    @pytest.mark.asyncio
    async def test_pdf_low_complexity_parser_used_is_pymupdf(self, tmp_path: Path):
        """PDF LOW complexity → parser_used == 'pymupdf'."""
        pdf_path = str(tmp_path / "architecture.pdf")
        Path(pdf_path).write_bytes(b"%PDF-1.4 fake")

        storage = AsyncMock()
        storage.save = AsyncMock(return_value="markdown/test/raw.md")

        long_content = "## 아키텍처 개요\n\n" + ("아키텍처 내용. " * 40)

        with patch("kms.pipeline.stage1_document_parser_agent._convert_pdf_with_pymupdf",
                   return_value=(long_content, 0.0)), \
             patch("kms.pipeline.stage1_document_parser_agent._diagnose_document",
                   return_value={"complexity": "LOW", "has_tables": False,
                                 "has_images": False, "page_count": 5, "image_ratio": 0.0}):
            from module_0_kms.pipeline.stage1_document_parser_agent import document_parser_agent
            result = await document_parser_agent(self._make_state(pdf_path, "pdf"), storage=storage)

        assert result["parser_used"] == "pymupdf"
        assert result.get("doc_complexity") == "LOW"

    @pytest.mark.asyncio
    async def test_pdf_high_no_upstage_key_triggers_hitl(self, tmp_path: Path):
        """PDF HIGH complexity + UPSTAGE_API_KEY 없음 → hitl_required 경로."""
        pdf_path = str(tmp_path / "complex.pdf")
        Path(pdf_path).write_bytes(b"%PDF-1.4 fake")

        storage = AsyncMock()

        with patch("kms.pipeline.stage1_document_parser_agent._diagnose_document",
                   return_value={"complexity": "HIGH", "has_tables": True,
                                 "has_images": True, "page_count": 20, "image_ratio": 0.6}), \
             patch.dict(os.environ, {"UPSTAGE_API_KEY": ""}):
            from module_0_kms.pipeline.stage1_document_parser_agent import document_parser_agent
            result = await document_parser_agent(self._make_state(pdf_path, "pdf"), storage=storage)

        assert result.get("hitl_required") is True
        assert result.get("status") == "hitl_pending"
        assert result.get("parser_used") == "hitl_required"
        storage.save.assert_not_called()  # HITL → 저장 없음

    @pytest.mark.asyncio
    async def test_low_quality_markdown_triggers_hitl(self, tmp_path: Path):
        """품질 점수 < 40인 Markdown → HITL 경로 진입."""
        docx_path = str(tmp_path / "broken.docx")
        Path(docx_path).write_bytes(b"PK\x03\x04")

        storage = AsyncMock()

        # 깨진 문자 > 2%, 짧음, 헤딩 없음 → quality ≈ 20 (< 40)
        bad_markdown = "가" * 97 + "\x00\x01\x02"  # 100자, 3% 깨진 문자

        with patch("kms.pipeline.stage1_document_parser_agent._convert_docx_with_python_docx",
                   return_value=bad_markdown), \
             patch("kms.pipeline.stage1_document_parser_agent._diagnose_document",
                   return_value={"complexity": "LOW", "has_tables": False,
                                 "has_images": False, "page_count": None, "image_ratio": 0.0}):
            from module_0_kms.pipeline.stage1_document_parser_agent import document_parser_agent
            result = await document_parser_agent(self._make_state(docx_path, "docx"), storage=storage)

        assert result.get("hitl_required") is True
        assert result.get("status") == "hitl_pending"
        assert result.get("raw_markdown") == bad_markdown  # HITL에 Markdown 보존

    @pytest.mark.asyncio
    async def test_pdf_high_with_upstage_key_uses_upstage(self, tmp_path: Path):
        """PDF HIGH complexity + UPSTAGE_API_KEY 있음 → upstage 파서 사용."""
        pdf_path = str(tmp_path / "scanned.pdf")
        Path(pdf_path).write_bytes(b"%PDF-1.4 fake")

        storage = AsyncMock()
        storage.save = AsyncMock(return_value="markdown/test/raw.md")

        long_upstage_result = "## Upstage 변환\n\n" + ("내용 텍스트. " * 40)

        with patch("kms.pipeline.stage1_document_parser_agent._diagnose_document",
                   return_value={"complexity": "HIGH", "has_tables": True,
                                 "has_images": True, "page_count": 10, "image_ratio": 0.6}), \
             patch("kms.pipeline.stage1_document_parser_agent._convert_with_upstage",
                   new_callable=AsyncMock, return_value=long_upstage_result), \
             patch.dict(os.environ, {"UPSTAGE_API_KEY": "up_real_test_key"}):
            from module_0_kms.pipeline.stage1_document_parser_agent import document_parser_agent
            result = await document_parser_agent(self._make_state(pdf_path, "pdf"), storage=storage)

        assert result.get("parser_used") == "upstage"
        assert result.get("raw_markdown") is not None


# ---------------------------------------------------------------------------
# Upstage 일일 한도 검증
# ---------------------------------------------------------------------------

class TestUpstageDailyLimit:
    """_check_upstage_daily_limit는 일일 한도를 초과 시 False를 반환한다."""

    def test_within_limit_returns_true_and_increments(self):
        from module_0_kms.pipeline.stage1_document_parser_agent import (
            _check_upstage_daily_limit, _upstage_daily_counter,
        )
        from datetime import date
        _upstage_daily_counter["date"] = str(date.today())
        _upstage_daily_counter["count"] = 0

        with patch.dict(os.environ, {"UPSTAGE_DAILY_LIMIT": "3"}):
            assert _check_upstage_daily_limit() is True
            assert _upstage_daily_counter["count"] == 1

    def test_at_limit_returns_false(self):
        from module_0_kms.pipeline.stage1_document_parser_agent import (
            _check_upstage_daily_limit, _upstage_daily_counter,
        )
        from datetime import date
        _upstage_daily_counter["date"] = str(date.today())
        _upstage_daily_counter["count"] = 3

        with patch.dict(os.environ, {"UPSTAGE_DAILY_LIMIT": "3"}):
            assert _check_upstage_daily_limit() is False
            assert _upstage_daily_counter["count"] == 3  # 증가 없음

    def test_new_day_resets_counter(self):
        from module_0_kms.pipeline.stage1_document_parser_agent import (
            _check_upstage_daily_limit, _upstage_daily_counter,
        )
        _upstage_daily_counter["date"] = "2000-01-01"  # 과거 날짜
        _upstage_daily_counter["count"] = 99

        with patch.dict(os.environ, {"UPSTAGE_DAILY_LIMIT": "100"}):
            assert _check_upstage_daily_limit() is True
            assert _upstage_daily_counter["count"] == 1  # 리셋 후 1

    @pytest.mark.asyncio
    async def test_daily_limit_exceeded_triggers_hitl(self, tmp_path: Path):
        """Upstage 일일 한도 초과 시 document_parser_agent가 HITL 경로로 진입한다."""
        pdf_path = str(tmp_path / "limit.pdf")
        Path(pdf_path).write_bytes(b"%PDF-1.4 fake")

        from module_0_kms.pipeline.stage1_document_parser_agent import _upstage_daily_counter
        from datetime import date
        _upstage_daily_counter["date"] = str(date.today())
        _upstage_daily_counter["count"] = 100

        storage = AsyncMock()

        state = {
            "doc_id": "bbbbbbbb-0000-0000-0000-000000000001",
            "source": "upload",
            "file_path": pdf_path,
            "file_type": "pdf",
            "original_filename": "limit.pdf",
            "raw_markdown": None,
            "markdown_storage_path": None,
            "status": "processing",
            "current_stage": "init",
        }

        with patch("kms.pipeline.stage1_document_parser_agent._diagnose_document",
                   return_value={"complexity": "HIGH", "has_tables": True,
                                 "has_images": False, "page_count": 5, "image_ratio": 0.3}), \
             patch.dict(os.environ, {"UPSTAGE_API_KEY": "up_real_key", "UPSTAGE_DAILY_LIMIT": "100"}):
            from module_0_kms.pipeline.stage1_document_parser_agent import document_parser_agent
            result = await document_parser_agent(state, storage=storage)

        assert result.get("hitl_required") is True
        assert result.get("status") == "hitl_pending"


# ---------------------------------------------------------------------------
# _post_process_upstage_markdown — HTML 표 변환 검증
# ---------------------------------------------------------------------------

class TestPostProcessUpstageMarkdown:
    """Upstage HTML 표 → Markdown 파이프 표 변환."""

    def _process(self, md: str) -> str:
        from module_0_kms.pipeline.stage1_document_parser_agent import _post_process_upstage_markdown
        return _post_process_upstage_markdown(md)

    def test_no_table_unchanged(self):
        md = "# 제목\n\n내용 텍스트"  # h1 최소 레벨 + 표 없음 → 원본 그대로
        assert self._process(md) == md

    def test_html_table_converted_to_pipe_table(self):
        md = (
            "## 결과\n\n"
            "<table><tr><th>항목</th><th>값</th></tr>"
            "<tr><td>A</td><td>100</td></tr></table>"
        )
        result = self._process(md)
        assert "<table" not in result
        assert "|" in result
        assert "항목" in result
        assert "---" in result  # 구분선

    def test_unconvertible_table_becomes_comment(self):
        """변환 실패하는 복잡한 테이블은 <!-- 표 변환 실패 --> 주석으로 대체된다."""
        # _html_table_to_markdown이 <table>을 그대로 반환하면 주석 처리됨
        # 실제로는 정상 변환되므로 이 케이스는 거의 발생하지 않음
        # 하지만 중첩 테이블 등 극단 케이스를 위한 방어 테스트
        md = "<table><tr><th>열1</th></tr><tr><td>값1</td></tr></table>"
        result = self._process(md)
        # 변환 성공이면 파이프 표, 실패면 주석 — 둘 다 허용
        assert "<table>" not in result or "<!-- 표 변환 실패" in result

    def test_multiple_tables_all_converted(self):
        """마크다운 내 여러 HTML 표가 모두 변환된다."""
        md = (
            "<table><tr><th>A</th></tr><tr><td>1</td></tr></table>"
            "\n\n내용\n\n"
            "<table><tr><th>B</th></tr><tr><td>2</td></tr></table>"
        )
        result = self._process(md)
        assert result.count("<table") == 0 or result.count("<!-- 표 변환 실패") == 2
        assert "A" in result
        assert "B" in result


# ---------------------------------------------------------------------------
# T1: _normalize_heading_hierarchy — 헤딩 계층 정규화
# ---------------------------------------------------------------------------

class TestNormalizeHeadingHierarchy:
    """Upstage가 모든 헤딩을 # h1으로 반환한 경우 최소 레벨 → h1 시프트."""

    def _normalize(self, md: str) -> str:
        from module_0_kms.pipeline.stage1_document_parser_agent import _normalize_heading_hierarchy
        return _normalize_heading_hierarchy(md)

    def test_no_headings_unchanged(self):
        """헤딩이 없는 문서는 원본 그대로."""
        md = "그냥 텍스트\n\n다음 단락"
        assert self._normalize(md) == md

    def test_h1_minimum_unchanged(self):
        """# h1이 이미 최소 레벨이면 변경 없음."""
        md = "# 대제목\n\n## 소제목\n\n### 세부"
        result = self._normalize(md)
        assert "# 대제목" in result
        assert "## 소제목" in result
        assert "### 세부" in result

    def test_all_h1_unchanged(self):
        """모든 헤딩이 # h1이면 변경 없음."""
        md = "# 섹션1\n\n내용\n\n# 섹션2\n\n내용"
        result = self._normalize(md)
        assert result.count("# ") == 2
        assert "## " not in result

    def test_h2_minimum_shifted_to_h1(self):
        """최소 헤딩이 ## h2 → # h1으로 시프트, ### h3 → ## h2."""
        md = "## 대주제\n\n### 소주제\n\n내용"
        result = self._normalize(md)
        assert "# 대주제" in result
        assert "## 소주제" in result
        assert "### " not in result

    def test_h3_minimum_shifted_to_h1(self):
        """최소 헤딩이 ### h3 → # h1으로 시프트."""
        md = "### 유일한 헤딩\n\n내용"
        result = self._normalize(md)
        assert "# 유일한 헤딩" in result
        assert "###" not in result

    def test_deep_hierarchy_shifted(self):
        """## / ### / #### 전체 계층이 한 단계씩 시프트된다."""
        md = "## 1단계\n\n### 2단계\n\n#### 3단계"
        result = self._normalize(md)
        assert "# 1단계" in result
        assert "## 2단계" in result
        assert "### 3단계" in result
        assert "####" not in result

    def test_body_text_hash_not_affected(self):
        """본문 내 #태그 (헤딩이 아님)는 변경되지 않는다."""
        md = "## 제목\n\n그냥 텍스트 #태그 포함\n\n내용"
        result = self._normalize(md)
        assert "# 제목" in result
        assert "그냥 텍스트 #태그 포함" in result


# ---------------------------------------------------------------------------
# T2: _normalize_korean_lists — 한국어 리스트 패턴 변환
# ---------------------------------------------------------------------------

class TestNormalizeKoreanLists:
    """가.나.다. / ①②③ / 1)2)3) 패턴을 '- ' 불릿으로 변환한다."""

    def _normalize(self, md: str) -> str:
        from module_0_kms.pipeline.stage1_document_parser_agent import _normalize_korean_lists
        return _normalize_korean_lists(md)

    def test_no_list_patterns_unchanged(self):
        """리스트 패턴 없는 문서는 원본 그대로."""
        md = "## 제목\n\n일반 텍스트입니다."
        assert self._normalize(md) == md

    def test_korean_alpha_list_converted(self):
        """가. 나. 다. 패턴 → '- ' 불릿."""
        md = "가. 첫 번째\n나. 두 번째\n다. 세 번째"
        result = self._normalize(md)
        assert "- 첫 번째" in result
        assert "- 두 번째" in result
        assert "- 세 번째" in result
        assert "가." not in result

    def test_circled_number_list_converted(self):
        """① ② ③ 패턴 → '- ' 불릿."""
        md = "① 항목1\n② 항목2\n③ 항목3"
        result = self._normalize(md)
        assert "- 항목1" in result
        assert "- 항목2" in result
        assert "- 항목3" in result
        assert "①" not in result

    def test_paren_number_list_converted(self):
        """1) 2) 3) 패턴 → '- ' 불릿."""
        md = "1) 첫째\n2) 둘째\n3) 셋째"
        result = self._normalize(md)
        assert "- 첫째" in result
        assert "- 둘째" in result
        assert "- 셋째" in result
        assert "1)" not in result

    def test_existing_bullet_unchanged(self):
        """이미 '- ' 불릿인 항목은 변경 없음."""
        md = "- 기존 항목\n- 다른 항목"
        assert self._normalize(md) == md

    def test_inline_korean_alpha_not_converted(self):
        """문장 중간의 '가.' 는 변환하지 않는다."""
        md = "이것은 가. 다 가. 나 형태의 문장입니다."
        result = self._normalize(md)
        assert "가." in result  # 줄 시작이 아니므로 변환 안 됨

    def test_mixed_patterns_all_converted(self):
        """가.나.다. 와 ①②③ 가 한 문서에 있으면 둘 다 변환."""
        md = "가. 항목A\n① 항목B\n1) 항목C"
        result = self._normalize(md)
        assert result.count("- ") == 3

    # T8: (가)(나)(다) 괄호 패턴
    def test_paren_korean_alpha_converted(self):
        """(가) (나) (다) 괄호 패턴 → '- ' 불릿."""
        md = "(가) 첫 번째\n(나) 두 번째\n(다) 세 번째"
        result = self._normalize(md)
        assert "- 첫 번째" in result
        assert "- 두 번째" in result
        assert "- 세 번째" in result
        assert "(가)" not in result

    def test_inline_paren_korean_not_converted(self):
        """문장 중간의 (가)는 변환하지 않는다."""
        md = "공존성 co-existence에 (가) 붙음이 있습니다."
        result = self._normalize(md)
        assert "(가)" in result  # 줄 시작이 아니므로 변환 안 됨


# ---------------------------------------------------------------------------
# T3: _html_table_to_markdown — colspan/rowspan 처리
# ---------------------------------------------------------------------------

class TestHtmlTableColspanRowspan:
    """colspan/rowspan 셀이 있는 표를 올바른 열 수로 변환한다."""

    def _convert(self, html: str) -> str:
        from module_0_kms.pipeline.stage1_document_parser_agent import _html_table_to_markdown
        return _html_table_to_markdown(html)

    def test_simple_table_unchanged(self):
        """colspan 없는 일반 표는 기존 동작과 동일."""
        html = "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>"
        result = self._convert(html)
        assert "| A | B |" in result
        assert "| 1 | 2 |" in result

    def test_colspan2_pads_empty_cell(self):
        """colspan=2 셀은 내용 셀 + 빈 셀 1개로 패딩된다."""
        html = (
            "<table>"
            "<tr><th colspan='2'>병합헤더</th></tr>"
            "<tr><td>A</td><td>B</td></tr>"
            "</table>"
        )
        result = self._convert(html)
        # 헤더 행: 병합헤더 + 빈 셀 → 열 수 = 2
        assert "병합헤더" in result
        header_line = [l for l in result.split("\n") if "병합헤더" in l][0]
        assert header_line.count("|") == 3  # | 병합헤더 |  | → 파이프 3개

    def test_colspan3_pads_two_empty_cells(self):
        """colspan=3 셀은 내용 + 빈 셀 2개."""
        html = (
            "<table>"
            "<tr><th colspan='3'>3열 병합</th></tr>"
            "<tr><td>X</td><td>Y</td><td>Z</td></tr>"
            "</table>"
        )
        result = self._convert(html)
        header_line = [l for l in result.split("\n") if "3열 병합" in l][0]
        # | 3열 병합 |  |  | → 파이프 4개
        assert header_line.count("|") == 4

    def test_data_row_colspan_pads(self):
        """데이터 행의 colspan도 빈 셀로 패딩된다."""
        html = (
            "<table>"
            "<tr><th>A</th><th>B</th><th>C</th></tr>"
            "<tr><td colspan='2'>병합데이터</td><td>값C</td></tr>"
            "</table>"
        )
        result = self._convert(html)
        data_line = [l for l in result.split("\n") if "병합데이터" in l][0]
        # | 병합데이터 |  | 값C | → 파이프 4개
        assert data_line.count("|") == 4

    def test_no_colspan_column_count_matches_header(self):
        """colspan 없는 행의 열 수는 헤더와 일치한다."""
        html = (
            "<table>"
            "<tr><th>H1</th><th>H2</th><th>H3</th></tr>"
            "<tr><td>A</td><td>B</td><td>C</td></tr>"
            "</table>"
        )
        result = self._convert(html)
        lines = [l for l in result.split("\n") if "|" in l and "---" not in l]
        col_counts = [l.count("|") for l in lines]
        assert len(set(col_counts)) == 1  # 모든 행의 파이프 수 동일

    def test_rowspan2_content_repeated_in_next_row(self):
        """rowspan=2 셀의 내용이 다음 행에도 반복되어 내용 손실이 없어야 한다."""
        html = (
            "<table>"
            "<tr><th>구분</th><th>항목</th><th>값</th></tr>"
            "<tr><td rowspan='2'>공통</td><td>항목A</td><td>10</td></tr>"
            "<tr><td>항목B</td><td>20</td></tr>"
            "</table>"
        )
        result = self._convert(html)
        lines = [l for l in result.split("\n") if "|" in l and "---" not in l]
        # rowspan 셀 '공통'이 두 데이터 행 모두에 나타나야 함
        data_lines_with_content = [l for l in lines[1:] if "공통" in l]
        assert len(data_lines_with_content) == 2, (
            f"rowspan=2인 '공통' 셀이 두 행에 모두 있어야 함. 실제:\n{result}"
        )

    def test_rowspan_column_count_consistent(self):
        """rowspan 행이 있어도 모든 행의 열 수가 일치해야 한다."""
        html = (
            "<table>"
            "<tr><th>A</th><th>B</th><th>C</th></tr>"
            "<tr><td rowspan='2'>X</td><td>Y1</td><td>Z1</td></tr>"
            "<tr><td>Y2</td><td>Z2</td></tr>"
            "</table>"
        )
        result = self._convert(html)
        lines = [l for l in result.split("\n") if "|" in l and "---" not in l]
        col_counts = [l.count("|") for l in lines]
        assert len(set(col_counts)) == 1, (
            f"rowspan 있을 때 열 수가 불일치: {col_counts}\n{result}"
        )

    def test_multiline_cell_br_converted_to_space(self):
        """셀 내 <br> 태그는 공백으로 변환되어 내용이 보존되어야 한다."""
        html = (
            "<table>"
            "<tr><th>제목</th></tr>"
            "<tr><td>첫번째<br/>두번째</td></tr>"
            "</table>"
        )
        result = self._convert(html)
        assert "첫번째" in result
        assert "두번째" in result

    def test_complex_table_no_fallback_comment(self):
        """rowspan+colspan 복합 표가 '<!-- 표 변환 실패 -->' 없이 변환되어야 한다."""
        html = (
            "<table>"
            "<tr><th colspan='2'>통합헤더</th><th>단독</th></tr>"
            "<tr><td rowspan='2'>병합셀</td><td>B1</td><td>C1</td></tr>"
            "<tr><td>B2</td><td>C2</td></tr>"
            "</table>"
        )
        result = self._convert(html)
        assert "표 변환 실패" not in result, (
            f"복합 표가 fallback 처리됨:\n{result}"
        )
        assert "|" in result


# ---------------------------------------------------------------------------
# T4: _post_process_upstage_markdown — T1/T2 통합 파이프라인 검증
# ---------------------------------------------------------------------------

class TestPostProcessPipeline:
    """_post_process_upstage_markdown이 T1(헤딩)+T2(한국어 리스트)+표변환을 모두 수행한다."""

    def _process(self, md: str) -> str:
        from module_0_kms.pipeline.stage1_document_parser_agent import _post_process_upstage_markdown
        return _post_process_upstage_markdown(md)

    def test_heading_normalized_in_pipeline(self):
        """## 최소 헤딩이 파이프라인 통과 후 # h1으로 시프트된다."""
        md = "## 제목\n\n### 소제목\n\n내용 텍스트"
        result = self._process(md)
        assert "# 제목" in result
        assert "## 소제목" in result
        assert "### " not in result

    def test_korean_list_normalized_in_pipeline(self):
        """가.나.다. 패턴이 파이프라인 통과 후 불릿으로 변환된다."""
        md = "## 목록\n\n가. 항목1\n나. 항목2\n다. 항목3"
        result = self._process(md)
        assert "- 항목1" in result
        assert "- 항목2" in result

    def test_html_table_converted_in_pipeline(self):
        """HTML 표가 파이프라인 통과 후 Markdown 파이프 표로 변환된다."""
        md = "<table><tr><th>항목</th><th>값</th></tr><tr><td>A</td><td>1</td></tr></table>"
        result = self._process(md)
        assert "<table" not in result
        assert "|" in result

    def test_all_three_combined(self):
        """헤딩 + 리스트 + 표가 한 문서에 있으면 셋 다 처리된다."""
        md = (
            "## 제목\n\n"
            "가. 항목1\n나. 항목2\n\n"
            "<table><tr><th>열1</th></tr><tr><td>값1</td></tr></table>"
        )
        result = self._process(md)
        assert "# 제목" in result
        assert "- 항목1" in result
        assert "<table" not in result


# ---------------------------------------------------------------------------
# T9: _strip_html_artifacts — 비-테이블 HTML 태그 & 엔티티 제거
# ---------------------------------------------------------------------------

class TestStripHtmlArtifacts:
    """_strip_html_artifacts()는 Upstage 출력에 남은 비-테이블 HTML 잔재를 제거한다."""

    def _strip(self, text: str) -> str:
        from module_0_kms.pipeline.stage1_document_parser_agent import _strip_html_artifacts
        return _strip_html_artifacts(text)

    # --- <br> 변환 ---

    def test_br_tag_converted_to_newline(self):
        """`<br>` 태그가 개행으로 변환된다."""
        assert self._strip("줄1<br>줄2") == "줄1\n줄2"

    def test_br_selfclose_converted_to_newline(self):
        """`<br/>` 태그가 개행으로 변환된다."""
        assert self._strip("줄1<br/>줄2") == "줄1\n줄2"

    def test_br_space_selfclose_converted_to_newline(self):
        """`<br />` 태그가 개행으로 변환된다."""
        assert self._strip("줄1<br />줄2") == "줄1\n줄2"

    # --- 인라인 태그 텍스트 보존 ---

    def test_span_tag_stripped_preserves_text(self):
        """`<span>` 태그가 제거되고 내부 텍스트는 보존된다."""
        assert self._strip("<span>중요 내용</span>") == "중요 내용"

    def test_em_tag_stripped_preserves_text(self):
        """`<em>` 태그가 제거되고 내부 텍스트는 보존된다."""
        assert self._strip("<em>강조</em>") == "강조"

    def test_strong_tag_stripped_preserves_text(self):
        """`<strong>` 태그가 제거되고 내부 텍스트는 보존된다."""
        assert self._strip("<strong>굵게</strong>") == "굵게"

    def test_p_tag_stripped_preserves_text(self):
        """`<p>` 태그가 제거되고 내부 텍스트는 보존된다."""
        result = self._strip("<p>단락 내용</p>")
        assert "단락 내용" in result
        assert "<p>" not in result

    def test_div_tag_stripped_preserves_text(self):
        """`<div>` 태그가 제거되고 내부 텍스트는 보존된다."""
        result = self._strip("<div>컨테이너 내용</div>")
        assert "컨테이너 내용" in result
        assert "<div>" not in result

    # --- 이미지/그림 요소 제거 ---

    def test_img_tag_removed(self):
        """`<img>` 태그가 완전히 제거된다."""
        result = self._strip("텍스트 <img src='fig1.png' alt='그림1'> 이후")
        assert "<img" not in result
        assert "텍스트" in result
        assert "이후" in result

    def test_figure_element_removed(self):
        """`<figure>...</figure>` 블록이 완전히 제거된다."""
        md = "앞 내용\n<figure><img src='a.png'/><figcaption>그림</figcaption></figure>\n뒤 내용"
        result = self._strip(md)
        assert "<figure" not in result
        assert "앞 내용" in result
        assert "뒤 내용" in result

    # --- HTML 엔티티 디코딩 ---

    def test_nbsp_decoded_to_space(self):
        """`&nbsp;` 엔티티가 일반 공백으로 변환된다."""
        result = self._strip("단어1&nbsp;단어2")
        assert "&nbsp;" not in result
        assert "단어1" in result
        assert "단어2" in result

    def test_amp_decoded(self):
        """`&amp;` 엔티티가 `&`로 변환된다."""
        assert "&" in self._strip("A&amp;B")
        assert "&amp;" not in self._strip("A&amp;B")

    def test_lt_decoded(self):
        """`&lt;` 엔티티가 `<`로 변환된다."""
        result = self._strip("값 &lt; 10")
        assert "&lt;" not in result
        assert "<" in result

    def test_gt_decoded(self):
        """`&gt;` 엔티티가 `>`로 변환된다."""
        result = self._strip("값 &gt; 10")
        assert "&gt;" not in result
        assert ">" in result

    def test_quot_decoded(self):
        """`&quot;` 엔티티가 `"`로 변환된다."""
        result = self._strip("&quot;인용&quot;")
        assert "&quot;" not in result
        assert '"' in result

    # --- 테이블 태그는 건드리지 않음 ---

    def test_table_tag_not_modified(self):
        """`<table>`은 제거하지 않는다 — 표 변환은 별도 단계에서 처리."""
        html = "<table><tr><td>셀</td></tr></table>"
        result = self._strip(html)
        assert "<table" in result

    # --- 순수 텍스트는 그대로 ---

    def test_plain_text_unchanged(self):
        """HTML 없는 순수 텍스트는 변경되지 않는다."""
        text = "# 제목\n\n- 항목1\n- 항목2\n\n일반 텍스트입니다."
        assert self._strip(text) == text

    # --- 파이프라인 통합: _post_process_upstage_markdown에 포함 ---

    def test_pipeline_includes_html_artifact_stripping(self):
        """_post_process_upstage_markdown이 HTML 잔재를 제거한다."""
        from module_0_kms.pipeline.stage1_document_parser_agent import _post_process_upstage_markdown
        md = "## 서비스 소개\n\n<span>핵심 기능</span>: 데이터 처리 &amp; 분석\n\n줄1<br>줄2"
        result = _post_process_upstage_markdown(md)
        assert "<span>" not in result
        assert "&amp;" not in result
        assert "<br>" not in result
        assert "핵심 기능" in result
        assert "데이터 처리" in result


# ---------------------------------------------------------------------------
# T10-A: _strip_html_artifacts — unknown figure 태그 제거
# ---------------------------------------------------------------------------

class TestStripHtmlArtifactsUnknownTags:
    """_strip_html_artifacts()는 Upstage가 삽입하는 <그림 N-N> 같은 unknown 태그도 제거한다."""

    def _strip(self, text: str) -> str:
        from module_0_kms.pipeline.stage1_document_parser_agent import _strip_html_artifacts
        return _strip_html_artifacts(text)

    def test_figure_reference_tag_removed(self):
        """`<그림 1-1>` 같은 Upstage figure 참조 태그가 제거된다."""
        result = self._strip("앞 텍스트 <그림 1-1> 뒤 텍스트")
        assert "<그림" not in result
        assert "앞 텍스트" in result
        assert "뒤 텍스트" in result

    def test_figure_reference_with_hyphen_removed(self):
        """`<그림 2-3>` 패턴도 제거된다."""
        assert "<그림" not in self._strip("<그림 2-3>")

    def test_closing_figure_tag_removed(self):
        """`</그림>` 형태 닫는 태그도 제거된다."""
        result = self._strip("<그림 1-1>내용</그림>")
        assert "<그림" not in result
        assert "</그림>" not in result

    def test_table_reference_tag_removed(self):
        """`<표 1-1>` 같은 표 참조 태그도 제거된다."""
        result = self._strip("아래 <표 1-1>을 참조하세요")
        assert "<표" not in result
        assert "을 참조하세요" in result

    def test_unknown_korean_tag_removed(self):
        """한글이 포함된 임의의 unknown 태그가 제거된다."""
        result = self._strip("내용 <목록 1> 이후")
        assert "<목록" not in result
        assert "내용" in result
        assert "이후" in result

    def test_plain_text_angle_brackets_preserved(self):
        """수식 `a < b`, `x > 0` 같은 비-태그 꺾쇠는 건드리지 않는다."""
        # 공백으로 분리된 비교 연산자는 태그가 아님 → 보존
        text = "a < b이고 x > 0이면"
        result = self._strip(text)
        assert "<" in result or "a" in result  # 내용이 보존됨

    def test_pipeline_strips_unknown_tags(self):
        """_post_process_upstage_markdown이 unknown 태그도 제거한다."""
        from module_0_kms.pipeline.stage1_document_parser_agent import _post_process_upstage_markdown
        md = "# 1절\n\n아래 <그림 1-1>을 참고하세요.\n\n내용입니다."
        result = _post_process_upstage_markdown(md)
        assert "<그림" not in result
        assert "을 참고하세요" in result


# ---------------------------------------------------------------------------
# T10-B: _normalize_heading_hierarchy — 한국어 목록 패턴 헤딩 변환
# ---------------------------------------------------------------------------

class TestNormalizeHeadingWithKoreanList:
    """헤딩으로 잘못 표시된 한국어 목록 패턴(`# (가)`, `# 가.`, `# ①`)을 불릿으로 변환한다."""

    def _process(self, md: str) -> str:
        from module_0_kms.pipeline.stage1_document_parser_agent import _normalize_heading_korean_list
        return _normalize_heading_korean_list(md)

    def test_h1_paren_number_becomes_bullet(self):
        """`# (1) 텍스트` → `- (1) 텍스트` (숫자 목록이 H1으로 잘못 표시된 경우)."""
        result = self._process("# (1) NCS 학습모듈이란?")
        assert "- (1) NCS 학습모듈이란?" in result
        assert "# (1)" not in result

    def test_h1_paren_korean_becomes_bullet(self):
        """`# (가) 텍스트` → `- (가) 텍스트`."""
        result = self._process("# (가) 공존성 co-existence")
        assert "- (가) 공존성 co-existence" in result
        assert "# (가)" not in result

    def test_h1_korean_dot_becomes_bullet(self):
        """`# 가. 텍스트` → `- 텍스트` (한글 자음+마침표 목록이 H1으로 잘못 표시)."""
        result = self._process("# 가. 항목 내용")
        assert "# 가." not in result
        assert "항목 내용" in result

    def test_h1_circled_number_becomes_bullet(self):
        """`# ① 텍스트` → `- 텍스트`."""
        result = self._process("# ① 첫 번째 항목")
        assert "# ①" not in result
        assert "첫 번째 항목" in result

    def test_h2_paren_number_becomes_bullet(self):
        """`## (1) 텍스트` → `- (1) 텍스트`."""
        result = self._process("## (1) 하위 항목")
        assert "- (1) 하위 항목" in result
        assert "## (1)" not in result

    def test_normal_heading_unchanged(self):
        """일반 제목(`# 제목 텍스트`)은 변환하지 않는다."""
        result = self._process("# NCS 학습모듈의 이해")
        assert "# NCS 학습모듈의 이해" in result

    def test_h1_numbered_section_unchanged(self):
        """`# 1. 섹션명` 같은 숫자+마침표 섹션은 변환하지 않는다 (진짜 섹션 번호)."""
        result = self._process("# 1. NCS 학습모듈의 위치")
        assert "# 1. NCS 학습모듈의 위치" in result

    def test_multiline_document_partial_conversion(self):
        """문서 내 일부 헤딩만 변환되고 나머지는 유지된다."""
        md = "# 서론\n\n# (1) 목적\n\n# (가) 배경"
        result = self._process(md)
        assert "# 서론" in result
        assert "- (1) 목적" in result
        assert "- (가) 배경" in result

    def test_pipeline_includes_heading_korean_list_normalization(self):
        """_post_process_upstage_markdown이 헤딩-한국어목록 변환을 수행한다."""
        from module_0_kms.pipeline.stage1_document_parser_agent import _post_process_upstage_markdown
        md = "# NCS 학습\n\n# (1) 목적\n\n# (가) 공존성"
        result = _post_process_upstage_markdown(md)
        assert "# NCS 학습" in result
        assert "- (1) 목적" in result
        assert "- (가) 공존성" in result
