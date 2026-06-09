"""
TDD: Stage 5 메타데이터 에이전트 — H1 헤딩 title 추출 테스트

_extract_h1_title(markdown) 함수:
- 첫 번째 # H1을 title로 반환
- H1이 없으면 None 반환
- ## H2는 무시
- 빈 문서, 공백만 있는 문서 처리
- # 뒤 텍스트가 없는 경우(빈 H1) 처리

_extract_metadata_with_h1_override():
- LLM이 반환한 title을 H1이 있으면 H1으로 덮어씀
- H1이 없으면 LLM title 유지
"""

import pytest

from app.pipeline.stage5_metadata_agent import _extract_h1_title


class TestExtractH1Title:
    def test_returns_h1_text(self):
        md = "# 대규모 언어 모델(LLM) 기술 개요\n\n본문 내용"
        assert _extract_h1_title(md) == "대규모 언어 모델(LLM) 기술 개요"

    def test_returns_first_h1_when_multiple(self):
        md = "# 첫 번째 제목\n\n## 섹션\n\n# 두 번째 제목"
        assert _extract_h1_title(md) == "첫 번째 제목"

    def test_ignores_h2_and_below(self):
        md = "## 섹션 제목\n\n### 소제목\n\n본문"
        assert _extract_h1_title(md) is None

    def test_returns_none_for_empty_string(self):
        assert _extract_h1_title("") is None

    def test_returns_none_for_whitespace_only(self):
        assert _extract_h1_title("   \n\n   ") is None

    def test_returns_none_for_no_headings(self):
        md = "그냥 본문입니다.\n두 번째 줄."
        assert _extract_h1_title(md) is None

    def test_strips_surrounding_whitespace_from_title(self):
        md = "#   공백이 있는 제목   \n\n본문"
        assert _extract_h1_title(md) == "공백이 있는 제목"

    def test_returns_none_for_empty_h1(self):
        md = "#\n\n본문"
        assert _extract_h1_title(md) is None

    def test_h1_with_inline_code(self):
        md = "# REST API `레퍼런스`\n\n본문"
        assert _extract_h1_title(md) == "REST API `레퍼런스`"

    def test_h1_not_at_start_of_file(self):
        """H1이 첫 줄이 아니어도 추출"""
        md = "---\nfront matter\n---\n\n# 문서 제목\n\n본문"
        assert _extract_h1_title(md) == "문서 제목"
