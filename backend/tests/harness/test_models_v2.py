"""단위 테스트 — app.domain.models (4-레이어 신 아키텍처).

DB 불필요. 순수 Pydantic 모델 검증.

커버:
  U01 _to_snake()             — 모든 포맷 → 소문자 스네이크케이스
  U02 MechanismIn             — mechanism_name 정규화
  U03 PropertyIn              — key 정규화
  U04 ConceptExtractionSchema — 구형 list[str] mechanism 수렴
  U05 ConceptExtractionSchema — 구형 flat code_examples 귀속
  U06 ConceptExtractionSchema — owasp_category → owasp_id 병합
  U07 ConceptExtractionSchema — domains 소문자 + neo4j_extra_labels
  U08 교차 도메인 — :Security:Performance 라벨 2개
  U09 build_doc_id()          — 결정론적 해시 + 콘텐츠 변경 시 다른 ID
  U10 ConceptUpdate.to_neo4j_dict() — None 필드 제외
"""

import pytest

from app.domain.models import (
    ConceptExtractionSchema,
    ConceptUpdate,
    MechanismIn,
    PropertyIn,
    _to_snake,
    build_doc_id,
)


# ─── U01: _to_snake ───────────────────────────────────────────────────────────


class TestToSnake:
    @pytest.mark.parametrize(
        "inp, expected",
        [
            ("OutputEncoding", "output_encoding"),
            ("outputEncoding", "output_encoding"),
            ("CSRFTokenValidation", "csrf_token_validation"),
            ("already_snake", "already_snake"),
            ("With Spaces", "with_spaces"),
            ("With-Hyphens", "with_hyphens"),
            ("ParameterizedQuery", "parameterized_query"),
            ("secure_browser_xss_filter", "secure_browser_xss_filter"),
        ],
    )
    def test_conversion(self, inp: str, expected: str):
        assert _to_snake(inp) == expected

    def test_no_leading_trailing_underscores(self):
        result = _to_snake("SomeName")
        assert not result.startswith("_")
        assert not result.endswith("_")


# ─── U02: MechanismIn ─────────────────────────────────────────────────────────


class TestMechanismIn:
    def test_camel_normalized(self):
        assert (
            MechanismIn(mechanism_name="OutputEncoding").mechanism_name
            == "output_encoding"
        )

    def test_already_snake_unchanged(self):
        assert (
            MechanismIn(mechanism_name="parameterized_query").mechanism_name
            == "parameterized_query"
        )

    def test_space_normalized(self):
        result = MechanismIn(mechanism_name="CSRF Token Validation").mechanism_name
        assert " " not in result
        assert result == result.lower()

    def test_code_examples_default_empty(self):
        assert MechanismIn(mechanism_name="m").code_examples == []


# ─── U03: PropertyIn ──────────────────────────────────────────────────────────


class TestPropertyIn:
    def test_camel_key_normalized(self):
        p = PropertyIn(key="SecureBrowserXssFilter", value="True")
        assert p.key == "secure_browser_xss_filter"

    def test_upper_key_normalized(self):
        p = PropertyIn(key="CSRF_COOKIE_SECURE", value="True")
        assert p.key == p.key.lower()

    def test_type_default_security(self):
        assert PropertyIn(key="k", value="v").type == "security"

    def test_type_tuning_accepted(self):
        assert PropertyIn(key="k", value="v", type="tuning").type == "tuning"

    def test_type_invalid_raises(self):
        with pytest.raises(Exception):
            PropertyIn(key="k", value="v", type="invalid_type")


# ─── U04: 구형 list[str] mechanism → MechanismIn 수렴 ────────────────────────


class TestLegacyMechanismStrList:
    def test_string_list_converted(self):
        c = ConceptExtractionSchema(
            concept_name="XSS",
            security_mechanism=["OutputEncoding", "ContentSecurityPolicy"],
        )
        assert len(c.mechanisms) == 2
        assert all(isinstance(m, MechanismIn) for m in c.mechanisms)
        assert c.mechanisms[0].mechanism_name == "output_encoding"
        assert c.mechanisms[1].mechanism_name == "content_security_policy"

    def test_dict_mechanism_converted(self):
        c = ConceptExtractionSchema(
            concept_name="SQLi",
            security_mechanism=[
                {"mechanism_name": "ParameterizedQuery", "code_examples": []}
            ],
        )
        assert c.mechanisms[0].mechanism_name == "parameterized_query"

    def test_mixed_str_and_dict(self):
        c = ConceptExtractionSchema(
            concept_name="CSRF",
            security_mechanism=[
                "CsrfTokenValidation",
                {"mechanism_name": "SameSiteCookie", "code_examples": []},
            ],
        )
        assert len(c.mechanisms) == 2
        assert all(isinstance(m, MechanismIn) for m in c.mechanisms)

    def test_empty_mechanism_list_ok(self):
        c = ConceptExtractionSchema(concept_name="X", security_mechanism=[])
        assert c.mechanisms == []


# ─── U05: 구형 flat code_examples 귀속 ────────────────────────────────────────


class TestFlatCodeExamplesCoercion:
    def test_attaches_to_first_empty_mechanism(self):
        c = ConceptExtractionSchema(
            concept_name="CSRF",
            security_mechanism=["csrf_token"],
            code_examples=[{"lang": "python", "framework": "django", "code": "pass"}],
        )
        assert c.code_examples == []
        assert len(c.mechanisms[0].code_examples) == 1
        assert c.mechanisms[0].code_examples[0].lang == "python"

    def test_creates_default_mechanism_when_no_mechanism(self):
        c = ConceptExtractionSchema(
            concept_name="CsrfExempt",
            security_mechanism=[],
            code_examples=[{"lang": "html", "framework": "django", "code": "<form>"}],
        )
        assert c.code_examples == []
        assert len(c.mechanisms) == 1
        assert c.mechanisms[0].mechanism_name == "general_mitigation"

    def test_extends_first_mechanism_when_all_have_examples(self):
        c = ConceptExtractionSchema(
            concept_name="XSS",
            security_mechanism=[
                {
                    "mechanism_name": "output_encoding",
                    "code_examples": [
                        {"lang": "python", "framework": "django", "code": "a"}
                    ],
                },
            ],
            code_examples=[{"lang": "javascript", "framework": "react", "code": "b"}],
        )
        assert len(c.mechanisms[0].code_examples) == 2


# ─── U06: owasp_category → owasp_id 수렴 ─────────────────────────────────────


class TestOwaspCategoryMerge:
    def test_category_becomes_owasp_id(self):
        c = ConceptExtractionSchema(concept_name="XSS", owasp_category="A03:2025")
        assert c.owasp_id == "A03:2025"

    def test_owasp_id_takes_precedence(self):
        c = ConceptExtractionSchema(
            concept_name="XSS",
            owasp_id="A01:2025",
            owasp_category="A03:2025",
        )
        assert c.owasp_id == "A01:2025"

    def test_both_none_ok(self):
        c = ConceptExtractionSchema(concept_name="X")
        assert c.owasp_id is None


# ─── U07: domains 소문자 + neo4j_extra_labels ─────────────────────────────────


class TestDomainsAndLabels:
    def test_domains_lowercased(self):
        c = ConceptExtractionSchema(
            concept_name="X", domains=["Security", "PERFORMANCE"]
        )
        assert c.domains == ["security", "performance"]

    def test_security_label(self):
        c = ConceptExtractionSchema(concept_name="X", domains=["security"])
        assert c.neo4j_extra_labels == ["Security"]

    def test_performance_label(self):
        c = ConceptExtractionSchema(concept_name="X", domains=["performance"])
        assert c.neo4j_extra_labels == ["Performance"]

    def test_unknown_domain_ignored(self):
        c = ConceptExtractionSchema(concept_name="X", domains=["unknown"])
        assert c.neo4j_extra_labels == []


# ─── U08: 교차 도메인 ─────────────────────────────────────────────────────────


class TestCrossDomainLabels:
    def test_both_domains_produce_two_labels(self):
        c = ConceptExtractionSchema(
            concept_name="MemoryLeak",
            domains=["security", "performance"],
        )
        labels = c.neo4j_extra_labels
        assert "Security" in labels
        assert "Performance" in labels
        assert len(labels) == 2

    def test_concept_name_trimmed(self):
        c = ConceptExtractionSchema(concept_name="  XSS  ")
        assert c.concept_name == "XSS"


# ─── U09: build_doc_id ────────────────────────────────────────────────────────


class TestBuildDocId:
    URL = "https://docs.djangoproject.com/en/5.0/topics/security/"

    def test_deterministic(self):
        assert build_doc_id("EXT", self.URL, content="v1") == build_doc_id(
            "EXT", self.URL, content="v1"
        )

    def test_prefix_in_result(self):
        assert build_doc_id("EXT", self.URL).startswith("EXT_")
        assert build_doc_id("INT", self.URL).startswith("INT_")

    def test_different_content_different_id(self):
        assert build_doc_id("EXT", self.URL, content="v1") != build_doc_id(
            "EXT", self.URL, content="v2"
        )

    def test_etag_takes_priority_over_content(self):
        id_etag = build_doc_id("EXT", self.URL, content="ignored", etag="etag123")
        id_content = build_doc_id("EXT", self.URL, content="etag123")
        assert id_etag == id_content

    def test_hash_suffix_is_8_chars(self):
        doc_id = build_doc_id("EXT", self.URL, content="x")
        suffix = doc_id.rsplit("_", 1)[-1]
        assert len(suffix) == 8


# ─── U10: ConceptUpdate.to_neo4j_dict ────────────────────────────────────────


class TestConceptUpdate:
    def test_none_fields_excluded(self):
        d = ConceptUpdate(severity="high").to_neo4j_dict()
        assert "severity" in d
        assert "cwe_id" not in d
        assert "domains" not in d

    def test_domains_lowercased(self):
        d = ConceptUpdate(domains=["Security", "PERFORMANCE"]).to_neo4j_dict()
        assert d["domains"] == ["security", "performance"]

    def test_empty_returns_empty_dict(self):
        assert ConceptUpdate().to_neo4j_dict() == {}

    def test_is_deprecated_flag(self):
        assert (
            ConceptUpdate(is_deprecated=True).to_neo4j_dict()["is_deprecated"] is True
        )
