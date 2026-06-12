"""
test_tool_router_agent.py — tool_router_agent 단위 테스트
"""

import pytest
from dev2.nodes.tool_router_agent import build_tool_plan, tool_router_agent_node
from dev2.schema import Dev2State


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

def _diff(filepath: str, added_line: str = "") -> str:
    return (
        f"diff --git a/{filepath} b/{filepath}\n"
        f"--- a/{filepath}\n"
        f"+++ b/{filepath}\n"
        f"@@ -1,3 +1,4 @@\n"
        f" context\n"
        f"+{added_line}\n"
    )


# ── 1. Python auth 파일 + SQL 문자열 ─────────────────────────────────────────

class TestPythonAuthSql:
    DIFF = _diff("src/auth.py", "query = 'SELECT * FROM users WHERE id = ' + user_id")

    def test_selected_tools_include_pylint_radon(self):
        plan = build_tool_plan(self.DIFF, [], [])
        assert "pylint" in plan.selected_tools
        assert "radon" in plan.selected_tools

    def test_selected_tools_include_bandit_semgrep(self):
        plan = build_tool_plan(self.DIFF, [], [])
        assert "bandit" in plan.selected_tools
        assert "semgrep" in plan.selected_tools

    def test_llm_required_true(self):
        plan = build_tool_plan(self.DIFF, [], [])
        assert plan.llm_required is True

    def test_risk_keywords_detected(self):
        plan = build_tool_plan(self.DIFF, [], [])
        assert len(plan.risk_keywords) > 0

    def test_changed_files_contains_auth_py(self):
        plan = build_tool_plan(self.DIFF, [], [])
        assert any("auth.py" in f for f in plan.changed_files)


# ── 2. CSS만 변경 ─────────────────────────────────────────────────────────────

class TestCssOnly:
    DIFF = _diff("styles/main.css", ".container { color: red; }")

    def test_only_stylelint_selected(self):
        plan = build_tool_plan(self.DIFF, [], [])
        assert "stylelint" in plan.selected_tools

    def test_no_security_tools(self):
        plan = build_tool_plan(self.DIFF, [], [])
        assert "bandit" not in plan.selected_tools
        assert "eslint" not in plan.selected_tools
        assert "npm_audit" not in plan.selected_tools

    def test_llm_required_false(self):
        plan = build_tool_plan(self.DIFF, [], [])
        assert plan.llm_required is False


# ── 3. package.json 변경 ──────────────────────────────────────────────────────

class TestPackageJson:
    DIFF = _diff("package.json", '"lodash": "4.17.15"')

    def test_npm_audit_selected(self):
        plan = build_tool_plan(self.DIFF, [], [])
        assert "npm_audit" in plan.selected_tools

    def test_dependency_changed_true(self):
        plan = build_tool_plan(self.DIFF, [], [])
        assert plan.dependency_changed is True


# ── 4. requirements.txt 변경 ──────────────────────────────────────────────────

class TestRequirementsTxt:
    DIFF = _diff("requirements.txt", "django==4.2.0")

    def test_pip_audit_selected(self):
        plan = build_tool_plan(self.DIFF, [], [])
        assert "pip_audit" in plan.selected_tools

    def test_dependency_changed_true(self):
        plan = build_tool_plan(self.DIFF, [], [])
        assert plan.dependency_changed is True


# ── 5. previous_pr_issues에 SQL Injection ─────────────────────────────────────

class TestSecurityHistory:
    DIFF = _diff("src/views.py", "def get_user(): pass")

    def test_bandit_added_on_sql_injection_history(self):
        plan = build_tool_plan(self.DIFF, ["python"], ["SQL Injection 발견"])
        assert "bandit" in plan.selected_tools or "semgrep" in plan.selected_tools

    def test_llm_required_true_on_security_history(self):
        plan = build_tool_plan(self.DIFF, [], ["SQL 인젝션 반복"])
        assert plan.llm_required is True

    def test_xss_history_triggers_security_scan(self):
        plan = build_tool_plan(self.DIFF, ["python"], ["XSS 이슈"])
        assert plan.llm_required is True

    def test_csrf_history(self):
        plan = build_tool_plan(self.DIFF, ["python"], ["CSRF 취약점"])
        assert plan.llm_required is True


# ── 6. JS/TS 파일 ─────────────────────────────────────────────────────────────

class TestJavaScript:
    DIFF = _diff("frontend/App.tsx", "const x = eval(userInput)")

    def test_eslint_selected(self):
        plan = build_tool_plan(self.DIFF, [], [])
        assert "eslint" in plan.selected_tools

    def test_semgrep_added_on_security_keyword(self):
        plan = build_tool_plan(self.DIFF, [], [])
        assert "semgrep" in plan.selected_tools


# ── 7. 알 수 없는 확장자 + 보안 키워드 ──────────────────────────────────────

class TestUnknownExtensionWithSecurity:
    DIFF = _diff("config/auth.yaml", "password: hardcoded123")

    def test_semgrep_selected_for_unknown_with_security_kw(self):
        plan = build_tool_plan(self.DIFF, [], [])
        assert "semgrep" in plan.selected_tools


# ── 8. ALLOWED_TOOLS 필터 ─────────────────────────────────────────────────────

class TestAllowedToolsFilter:
    def test_all_selected_tools_are_allowed(self):
        from dev2.nodes.tool_router_agent import ALLOWED_TOOLS
        diff = (
            _diff("src/auth.py", "sql + user") +
            _diff("styles/main.css", ".a {}") +
            _diff("package.json", '"x": "1"')
        )
        plan = build_tool_plan(diff, ["django"], ["SQL Injection"])
        for tool in plan.selected_tools:
            assert tool in ALLOWED_TOOLS, f"{tool} not in ALLOWED_TOOLS"


# ── 9. LangGraph 노드 통합 ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tool_router_agent_node_returns_tool_plan():
    state: Dev2State = {
        "task_id": "t1", "pr_id": "1",
        "pr_diff": _diff("src/auth.py", "query = sql + user"),
        "developer_id": "dev-001", "skill_level": "junior",
        "tech_stack": ["python", "django"],
        "architecture_docs": [], "coding_conventions": "",
        "previous_pr_issues": [],
        "static_raw": [], "security_raw": [], "enriched": [], "final_output": [],
        "tool_plan": None, "action_decision": None,
    }
    result = await tool_router_agent_node(state)
    assert "tool_plan" in result
    tp = result["tool_plan"]
    assert isinstance(tp["selected_tools"], list)
    assert len(tp["selected_tools"]) > 0


@pytest.mark.asyncio
async def test_tool_router_agent_node_empty_diff():
    state: Dev2State = {
        "task_id": "t2", "pr_id": "2", "pr_diff": "",
        "developer_id": "dev-001", "skill_level": "junior",
        "tech_stack": [], "architecture_docs": [], "coding_conventions": "",
        "previous_pr_issues": [], "static_raw": [], "security_raw": [],
        "enriched": [], "final_output": [], "tool_plan": None, "action_decision": None,
    }
    result = await tool_router_agent_node(state)
    assert "tool_plan" in result
    assert result["tool_plan"]["selected_tools"] == []
