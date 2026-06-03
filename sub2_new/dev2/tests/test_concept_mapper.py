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
    build_code_context,
    build_taxonomy,
    _lookup_concept,
)
from dev2.schema import (
    Issue, AgentOutput, Summary, LearningContext, CodeContext, IssueTaxonomy,
)


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


# ── build_code_context 테스트 ─────────────────────────────────────────────────

class TestBuildCodeContext:
    SAMPLE_DIFF = """\
diff --git a/src/views.py b/src/views.py
--- a/src/views.py
+++ b/src/views.py
@@ -1,5 +1,7 @@
 def get_user(request):
     username = request.GET['username']
+    query = "SELECT * FROM auth_user WHERE username = '%s'" % username
+    users = User.objects.raw(query)
     return render(request, "list.html")
"""

    def test_extracts_issue_line_and_surrounding_context(self):
        # 위 diff에서 query 라인은 새 파일 기준 3번 라인
        ctx = build_code_context(self.SAMPLE_DIFF, "src/views.py", 3,
                                 "snippet_unavailable", "SQL Injection", "SQL 인젝션")
        assert "SELECT" in ctx["issue_line"]
        assert isinstance(ctx["context_before"], list)
        assert isinstance(ctx["context_after"], list)
        # 앞 라인에 함수 정의가 포함돼야 함
        assert any("def get_user" in line for line in ctx["context_before"])

    def test_preserves_indentation_in_context(self):
        ctx = build_code_context(self.SAMPLE_DIFF, "src/views.py", 3,
                                 "snippet_unavailable", "SQL Injection", "SQL 인젝션")
        # username 라인은 들여쓰기가 보존돼야 함
        assert any(line.startswith("    username") for line in ctx["context_before"])

    def test_context_summary_never_empty(self):
        ctx = build_code_context(self.SAMPLE_DIFF, "src/views.py", 3,
                                 "snippet_unavailable", "SQL Injection", "SQL 인젝션")
        assert ctx["context_summary"] != ""
        assert isinstance(ctx["context_summary"], str)

    def test_falls_back_to_code_snippet_when_line_not_found(self):
        # diff에 없는 라인 → issue_line = code_snippet
        ctx = build_code_context(self.SAMPLE_DIFF, "src/views.py", 9999,
                                 "query = sql + username", "SQL Injection", "msg")
        assert ctx["issue_line"] == "query = sql + username"
        assert ctx["context_before"] == []
        assert ctx["context_after"] == []

    def test_falls_back_to_unavailable_when_no_snippet(self):
        # diff에도 없고 snippet도 없음 → "snippet_unavailable"
        ctx = build_code_context("", "src/views.py", 1, "snippet_unavailable", "", "")
        assert ctx["issue_line"] == "snippet_unavailable"

    def test_summary_uses_message_when_concept_unknown(self):
        ctx = build_code_context("", "a.py", 1, "snippet_unavailable", "", "줄이 너무 깁니다")
        assert ctx["context_summary"] != ""
        assert "줄이 너무 깁니다" in ctx["context_summary"]


# ── build_taxonomy 테스트 ─────────────────────────────────────────────────────

class TestBuildTaxonomy:
    def test_b608_is_sql_injection(self):
        tax = build_taxonomy("B608", "raw_query", "SQL 인젝션", "", "Vulnerability")
        assert tax["category"] == "Security"
        assert tax["subcategory"] == "Injection"
        assert tax["issue_type"] == "SQL Injection"
        assert tax["sub_issue_type"] == "Raw Query String Formatting"

    def test_no_parameterize_is_missing_parameterized_query(self):
        tax = build_taxonomy("X", "no_parameterize", "", "", "")
        assert tax["sub_issue_type"] == "Missing Parameterized Query"

    def test_mark_safe_detected_from_code(self):
        tax = build_taxonomy("X", "", "", "return mark_safe(user_input)", "")
        assert tax["subcategory"] == "XSS"
        assert tax["sub_issue_type"] == "mark_safe Misuse"

    def test_safe_filter_detected_from_code(self):
        tax = build_taxonomy("X", "", "", "{{ comment|safe }}", "")
        assert tax["issue_type"] == "Cross-Site Scripting"
        assert tax["sub_issue_type"] == "Template Safe Filter Misuse"

    def test_inner_html_detected_from_code(self):
        tax = build_taxonomy("X", "", "", "el.innerHTML = data", "")
        assert tax["sub_issue_type"] == "Direct innerHTML Assignment"

    def test_csrf_exempt_detected(self):
        tax = build_taxonomy("X", "", "", "@csrf_exempt", "")
        assert tax["subcategory"] == "CSRF"
        assert tax["sub_issue_type"] == "csrf_exempt Misuse"

    def test_no_login_required_is_auth(self):
        tax = build_taxonomy("X", "no_login_required", "", "", "")
        assert tax["subcategory"] == "Authentication & Authorization"
        assert tax["sub_issue_type"] == "Missing login_required"

    def test_no_permission_check_is_authz_bypass(self):
        tax = build_taxonomy("X", "no_permission_check", "", "", "")
        assert tax["issue_type"] == "Authorization Bypass"

    def test_complexity_is_cyclomatic(self):
        tax = build_taxonomy("R1260", "", "Cyclomatic complexity is too high", "", "")
        assert tax["subcategory"] == "Complexity"
        assert tax["sub_issue_type"] == "High Cyclomatic Complexity"

    def test_general_lint_is_code_smell(self):
        tax = build_taxonomy("SA-E501", "", "line too long", "", "Code Smell")
        assert tax["category"] == "Code Quality"
        assert tax["sub_issue_type"] == "General Code Smell"

    def test_fallback_when_nothing_matches(self):
        tax = build_taxonomy("", "", "", "", "")
        assert tax["category"] == "General"
        assert tax["issue_type"] == "Unknown"
        assert tax["sub_issue_type"] == "General Review Issue"


# ── enrich_with_concept_mapping: code_context / taxonomy 통합 테스트 ──────────

class TestEnrichAddsM4FeedbackFields:
    BASE_ISSUE = {
        "severity": "Critical",
        "issue_type": "Vulnerability",
        "line": 3,
        "file": "src/views.py",
        "message": "SQL 인젝션 가능성",
        "rule_id": "B608",
        "suggestion": "파라미터화된 쿼리 사용",
        "resolution_example": "",
        "similar_issues": [],
        "_source": "security",
        "llm_judged": True,
    }

    SAMPLE_DIFF = """\
diff --git a/src/views.py b/src/views.py
--- a/src/views.py
+++ b/src/views.py
@@ -1,5 +1,7 @@
 def get_user(request):
     username = request.GET['username']
+    query = "SELECT * FROM auth_user WHERE username = '%s'" % username
+    users = User.objects.raw(query)
     return render(request, "list.html")
"""

    def test_b608_produces_sql_injection_taxonomy(self):
        result = enrich_with_concept_mapping(self.BASE_ISSUE, self.SAMPLE_DIFF, ["django"])
        assert result["taxonomy"]["issue_type"] == "SQL Injection"
        assert result["taxonomy"]["sub_issue_type"] == "Raw Query String Formatting"

    def test_code_context_present_with_non_empty_summary(self):
        result = enrich_with_concept_mapping(self.BASE_ISSUE, self.SAMPLE_DIFF, [])
        assert "code_context" in result
        assert result["code_context"]["context_summary"] != ""
        assert "SELECT" in result["code_context"]["issue_line"]

    def test_code_snippet_fallback_into_code_context(self):
        # diff 없음 → code_snippet "snippet_unavailable" → issue_line도 동일
        result = enrich_with_concept_mapping(self.BASE_ISSUE, "", [])
        assert result["code_snippet"] == "snippet_unavailable"
        assert result["code_context"]["issue_line"] == "snippet_unavailable"

    def test_existing_and_m4_fields_all_preserved(self):
        result = enrich_with_concept_mapping(self.BASE_ISSUE, self.SAMPLE_DIFF, [])
        # 기존 필드
        assert result["severity"] == "Critical"
        assert result["rule_id"] == "B608"
        assert result["llm_judged"] is True
        # 기존 M4 매핑 필드
        assert result["concept"] == "SQL Injection"
        assert result["code_snippet"] != ""
        assert isinstance(result["learning_context"], LearningContext)
        # 신규 M4 피드백 필드
        assert "code_context" in result
        assert "taxonomy" in result

    def test_result_passes_issue_pydantic(self):
        # code_context / taxonomy dict이 Issue Pydantic에 통과하는지 (store 경계 검증)
        result = enrich_with_concept_mapping(self.BASE_ISSUE, self.SAMPLE_DIFF, [])
        fields = {
            "severity", "issue_type", "line", "file", "message", "rule_id",
            "suggestion", "resolution_example", "status", "similar_issues",
            "concept", "mistake_type", "concept_id", "mistake_type_concept_id",
            "confidence_score", "code_snippet", "learning_context",
            "code_context", "taxonomy",
        }
        filtered = {k: v for k, v in result.items() if k in fields}
        issue = Issue(**filtered)
        assert isinstance(issue.code_context, CodeContext)
        assert isinstance(issue.taxonomy, IssueTaxonomy)
        assert issue.taxonomy.issue_type == "SQL Injection"
        assert issue.code_context.context_summary != ""
