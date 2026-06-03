"""
test_concept_mapper.py — concept_mapper 단위 테스트

요구사항 10번 기준:
    - B608 SQL Injection → concept="SQL Injection", mistake_type="raw_query"
    - confidence >= 0.8 → mistake_type_concept_id 채워짐
    - code_snippet 없을 때 "snippet_unavailable" fallback
    - 기존 AgentOutput 필드 사라지지 않음
"""

import pytest
from dev2.nodes.concept_mapper import (
    enrich_with_concept_mapping,
    extract_snippet,
    infer_learning_context,
    _lookup_concept,
)
from dev2.schema import Issue, AgentOutput, Summary, LearningContext


# ── _lookup_concept 테스트 ────────────────────────────────────────────────────

class TestLookupConcept:
    def test_b608_maps_to_sql_injection(self):
        result = _lookup_concept("B608", "SQL 인젝션 가능성")
        assert result["concept"] == "SQL Injection"
        assert result["mistake_type"] == "raw_query"
        assert result["concept_id"] == "sql_injection"
        assert result["mistake_type_concept_id"] == "sql_injection.raw_query"
        assert result["confidence_score"] >= 0.9

    def test_b703_maps_to_xss(self):
        result = _lookup_concept("B703", "Django mark_safe 사용")
        assert result["concept"] == "XSS"
        assert result["mistake_type"] == "mark_safe_misuse"

    def test_b506_maps_to_csrf(self):
        result = _lookup_concept("B506", "CSRF exempt 사용")
        assert result["concept"] == "CSRF"
        assert result["mistake_type"] == "csrf_exempt_misuse"

    def test_b105_maps_to_auth_vulnerability(self):
        result = _lookup_concept("B105", "하드코딩된 비밀번호")
        assert result["concept"] == "AUTH_VULNERABILITY"
        assert result["confidence_score"] >= 0.9

    def test_unknown_rule_falls_back_to_message_pattern(self):
        # rule_id 없지만 message에 SQL injection 패턴 있음
        result = _lookup_concept("UNKNOWN-999", "parameterized query 미사용으로 SQL 인젝션 가능")
        assert result["concept"] == "SQL Injection"

    def test_low_confidence_message_gets_general_mistake_type(self):
        # confidence < 0.8인 패턴은 mistake_type = "general"
        result = _lookup_concept("UNKNOWN", "XSS 가능성 있음")
        assert result["concept"] == "XSS"
        assert result["mistake_type"] == "general"

    def test_unmapped_returns_empty(self):
        result = _lookup_concept("SA-E501", "줄 너무 길다")
        assert result == {}


# ── confidence 기준 테스트 ────────────────────────────────────────────────────

class TestConfidenceThreshold:
    def test_high_confidence_has_full_mistake_type_id(self):
        result = _lookup_concept("B608", "SQL 인젝션")
        # confidence >= 0.8 → mistake_type_concept_id 채워짐
        assert result["confidence_score"] >= 0.8
        assert "." in result["mistake_type_concept_id"]
        assert result["mistake_type"] != "general"

    def test_low_confidence_mistake_type_is_general(self):
        # XSS 패턴 중 confidence 낮은 것
        result = _lookup_concept("UNKNOWN", "xss 위험")
        assert result["confidence_score"] < 0.8
        assert result["mistake_type"] == "general"
        assert result["mistake_type_concept_id"].endswith(".general")


# ── extract_snippet 테스트 ────────────────────────────────────────────────────

class TestExtractSnippet:
    SAMPLE_DIFF = """\
diff --git a/src/auth.py b/src/auth.py
--- a/src/auth.py
+++ b/src/auth.py
@@ -10,6 +10,7 @@ def login(request):
 def get_user(username):
     conn = sqlite3.connect("test.db")
+    query = "SELECT * FROM users WHERE name = '" + username + "'"
     cursor = conn.cursor()
     return cursor.fetchall()
"""

    def test_finds_added_line(self):
        snippet = extract_snippet(self.SAMPLE_DIFF, "src/auth.py", 12)
        assert snippet != "snippet_unavailable"
        assert "SELECT" in snippet or "query" in snippet

    def test_returns_unavailable_for_missing_file(self):
        snippet = extract_snippet(self.SAMPLE_DIFF, "nonexistent.py", 1)
        assert snippet == "snippet_unavailable"

    def test_returns_unavailable_for_empty_diff(self):
        snippet = extract_snippet("", "src/auth.py", 1)
        assert snippet == "snippet_unavailable"

    def test_returns_unavailable_not_empty_string(self):
        # 요구사항 8: 찾지 못하면 빈 문자열이 아니라 "snippet_unavailable"
        snippet = extract_snippet(self.SAMPLE_DIFF, "src/auth.py", 9999)
        assert snippet == "snippet_unavailable"
        assert snippet != ""


# ── infer_learning_context 테스트 ────────────────────────────────────────────

class TestInferLearningContext:
    def test_python_file_sets_python_language(self):
        lc = infer_learning_context("src/auth.py", [])
        assert lc.language == "python"

    def test_django_in_tech_stack_sets_django_framework(self):
        lc = infer_learning_context("src/auth.py", ["django", "postgresql"])
        assert lc.framework == "django"

    def test_fastapi_in_tech_stack(self):
        lc = infer_learning_context("src/main.py", ["fastapi"])
        assert lc.framework == "fastapi"

    def test_unknown_python_defaults_to_none_framework(self):
        lc = infer_learning_context("src/utils.py", [])
        assert lc.language == "python"
        assert lc.framework == "none"

    def test_domain_context_defaults_to_ecommerce(self):
        lc = infer_learning_context("src/auth.py", [])
        assert lc.domain_context == "ecommerce"

    def test_js_file(self):
        lc = infer_learning_context("frontend/App.jsx", [])
        assert lc.language == "javascript"


# ── enrich_with_concept_mapping 통합 테스트 ──────────────────────────────────

class TestEnrichWithConceptMapping:
    BASE_ISSUE = {
        "severity": "Critical",
        "issue_type": "Vulnerability",
        "line": 42,
        "file": "src/auth.py",
        "message": "SQL 인젝션 가능성",
        "rule_id": "B608",
        "suggestion": "파라미터화된 쿼리 사용",
        "resolution_example": "",
        "similar_issues": [],
        "_source": "security",
        "llm_judged": True,
    }

    SAMPLE_DIFF = (
        "diff --git a/src/auth.py b/src/auth.py\n"
        "--- a/src/auth.py\n"
        "+++ b/src/auth.py\n"
        "@@ -40,5 +40,5 @@\n"
        " def get_user(username):\n"
        "+    query = \"SELECT * FROM users WHERE name = '\" + username + \"'\"\n"
        "+    cursor.execute(query)\n"
        " return result\n"
    )

    def test_b608_gets_sql_injection_concept(self):
        result = enrich_with_concept_mapping(self.BASE_ISSUE, self.SAMPLE_DIFF, ["django"])
        assert result["concept"] == "SQL Injection"
        assert result["mistake_type"] == "raw_query"
        assert result["concept_id"] == "sql_injection"
        assert result["mistake_type_concept_id"] == "sql_injection.raw_query"

    def test_confidence_score_above_08_for_b608(self):
        result = enrich_with_concept_mapping(self.BASE_ISSUE, self.SAMPLE_DIFF, [])
        assert result["confidence_score"] >= 0.8

    def test_code_snippet_extracted_or_unavailable(self):
        result = enrich_with_concept_mapping(self.BASE_ISSUE, self.SAMPLE_DIFF, [])
        assert result["code_snippet"] != ""  # 빈 문자열 아님
        # "snippet_unavailable" 또는 실제 코드
        assert isinstance(result["code_snippet"], str)

    def test_snippet_unavailable_fallback(self):
        # diff 없을 때 "snippet_unavailable" 반환
        result = enrich_with_concept_mapping(self.BASE_ISSUE, "", [])
        assert result["code_snippet"] == "snippet_unavailable"

    def test_learning_context_is_learning_context_instance(self):
        result = enrich_with_concept_mapping(self.BASE_ISSUE, "", ["django"])
        assert isinstance(result["learning_context"], LearningContext)
        assert result["learning_context"].framework == "django"
        assert result["learning_context"].language == "python"

    def test_existing_fields_preserved(self):
        # 기존 AgentOutput 필드가 사라지지 않아야 함
        result = enrich_with_concept_mapping(self.BASE_ISSUE, "", [])
        assert result["severity"] == "Critical"
        assert result["line"] == 42
        assert result["file"] == "src/auth.py"
        assert result["message"] == "SQL 인젝션 가능성"
        assert result["rule_id"] == "B608"
        assert result["suggestion"] == "파라미터화된 쿼리 사용"
        assert result["similar_issues"] == []
        assert result["llm_judged"] is True  # 내부 필드도 유지

    def test_already_mapped_issue_not_overwritten(self):
        # concept이 이미 있으면 덮어쓰지 않음
        issue_with_concept = {**self.BASE_ISSUE, "concept": "CUSTOM_CONCEPT"}
        result = enrich_with_concept_mapping(issue_with_concept, "", [])
        assert result["concept"] == "CUSTOM_CONCEPT"

    def test_unmapped_issue_has_empty_concept(self):
        lint_issue = {
            **self.BASE_ISSUE,
            "rule_id": "SA-E501",
            "message": "줄이 너무 길다 (120 > 79)",
            "severity": "Minor",
        }
        result = enrich_with_concept_mapping(lint_issue, "", [])
        assert result["concept"] == ""
        assert result["confidence_score"] == 0.0


# ── AgentOutput Pydantic 통과 테스트 ─────────────────────────────────────────

class TestAgentOutputPydantic:
    def test_issue_with_m4_fields_passes_pydantic(self):
        """M4 필드가 추가된 Issue가 AgentOutput Pydantic 검증을 통과하는지 확인"""
        from dev2.schema import Issue, LearningContext

        issue = Issue(
            severity="Critical",
            line=42,
            file="src/auth.py",
            message="SQL 인젝션",
            rule_id="B608",
            suggestion="파라미터화된 쿼리",
            concept="SQL Injection",
            mistake_type="raw_query",
            concept_id="sql_injection",
            mistake_type_concept_id="sql_injection.raw_query",
            confidence_score=0.92,
            code_snippet="query = sql + username",
            learning_context=LearningContext(
                framework="django",
                language="python",
                domain_context="ecommerce",
            ),
        )
        assert issue.concept == "SQL Injection"
        assert issue.learning_context.framework == "django"

    def test_issue_model_dump_includes_m4_fields(self):
        """model_dump() 결과에 M4 필드 포함 확인"""
        from dev2.schema import Issue
        issue = Issue(
            severity="Major",
            line=10,
            file="app.py",
            message="복잡도",
            rule_id="SA-001",
            suggestion="분리",
        )
        dumped = issue.model_dump()
        # M4 필드가 model_dump에 포함돼야 함
        assert "concept" in dumped
        assert "mistake_type" in dumped
        assert "confidence_score" in dumped
        assert "code_snippet" in dumped
        assert "learning_context" in dumped

    def test_existing_fields_not_removed_from_schema(self):
        """기존 필드 유지 확인"""
        from dev2.schema import Issue
        issue = Issue(
            severity="Minor",
            line=1,
            file="a.py",
            message="lint",
            rule_id="E501",
            suggestion="fix",
        )
        dumped = issue.model_dump()
        for field in ["severity", "issue_type", "line", "file", "message",
                      "rule_id", "suggestion", "resolution_example", "similar_issues"]:
            assert field in dumped, f"{field} 필드가 model_dump에 없음"
