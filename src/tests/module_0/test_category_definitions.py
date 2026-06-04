"""TDD — _category_definitions 공통 모듈 테스트.

stage5 와 stage5b 가 동일한 카테고리 정의를 공유해야 한다.
"""

from __future__ import annotations


class TestCategoryDefinitions:
    def test_all_six_categories_present(self):
        """6개 카테고리 모두 정의되어 있어야 한다."""
        from module_0_kms.pipeline._category_definitions import CATEGORY_DEFINITIONS
        expected = {"코딩컨벤션", "아키텍처", "온보딩", "보안", "배포", "기타"}
        assert set(CATEGORY_DEFINITIONS.keys()) == expected

    def test_each_definition_is_non_empty(self):
        """각 카테고리 정의가 비어있지 않아야 한다."""
        from module_0_kms.pipeline._category_definitions import CATEGORY_DEFINITIONS
        for name, definition in CATEGORY_DEFINITIONS.items():
            assert definition.strip(), f"'{name}' 카테고리 정의가 비어있음"

    def test_architecture_includes_ncs_keyword(self):
        """'아키텍처' 정의에 NCS SW아키텍처 관련 키워드가 포함되어야 한다.

        이 PDF가 '기타'로 잘못 분류된 원인을 방지:
        LM2001020101_SW아키텍처수행관리.pdf 는 NCS 교육 자료이므로
        정의에 NCS 관련 내용이 있어야 Stage5 LLM이 '아키텍처'를 선택한다.
        """
        from module_0_kms.pipeline._category_definitions import CATEGORY_DEFINITIONS
        arch_def = CATEGORY_DEFINITIONS["아키텍처"]
        assert "NCS" in arch_def or "수행" in arch_def or "교육" in arch_def, (
            f"'아키텍처' 정의에 NCS/수행/교육 키워드 없음: {arch_def}"
        )

    def test_giteo_is_last_resort(self):
        """'기타'는 마지막 수단임을 명시해야 한다 — LLM이 남용하지 않도록."""
        from module_0_kms.pipeline._category_definitions import CATEGORY_DEFINITIONS
        giteo_def = CATEGORY_DEFINITIONS["기타"]
        assert "마지막" in giteo_def or "해당하지" in giteo_def, (
            f"'기타' 정의에 '마지막 수단' 안내 없음: {giteo_def}"
        )

    def test_prompt_snippet_is_importable(self):
        """LLM 프롬프트에 삽입할 텍스트 스니펫이 제공되어야 한다."""
        from module_0_kms.pipeline._category_definitions import build_category_prompt_snippet
        snippet = build_category_prompt_snippet()
        assert isinstance(snippet, str)
        assert "아키텍처" in snippet
        assert "기타" in snippet
        assert len(snippet) > 50
