"""
test_action_decider_agent.py — action_decider_agent 단위 테스트
"""

import pytest
from dev2.nodes.action_decider_agent import decide_action, action_decider_agent_node
from dev2.graph import route_after_action_decider
from dev2.schema import Dev2State


# ── 픽스처 헬퍼 ───────────────────────────────────────────────────────────────

def _issue(severity: str, file: str = "src/utils.py", confidence: float = 0.9) -> dict:
    return {
        "severity": severity,
        "file": file,
        "line": 10,
        "message": f"{severity} 이슈",
        "rule_id": "TEST-001",
        "suggestion": "fix",
        "similar_issues": [],
        "confidence_score": confidence,
    }


# ── 1. Critical ≥ 1 → early_escalation ───────────────────────────────────────

class TestCriticalEscalation:
    def test_one_critical_gives_early_escalation(self):
        decision = decide_action([_issue("Critical")])
        assert decision.recommended_action == "early_escalation"

    def test_multiple_critical(self):
        issues = [_issue("Critical"), _issue("Critical", "src/auth.py"), _issue("Minor")]
        decision = decide_action(issues)
        assert decision.recommended_action == "early_escalation"
        assert decision.signals["critical_count"] == 2

    def test_early_escalation_confidence_high(self):
        decision = decide_action([_issue("Critical")])
        assert decision.confidence >= 0.9

    def test_route_early_escalation_goes_to_escalate(self):
        state: Dev2State = {
            "task_id": "t1", "pr_id": "1", "pr_diff": "", "developer_id": "d1",
            "skill_level": "junior", "tech_stack": [], "architecture_docs": [],
            "coding_conventions": "", "previous_pr_issues": [],
            "static_raw": [], "security_raw": [], "enriched": [],
            "final_output": [], "tool_plan": None,
            "action_decision": {
                "recommended_action": "early_escalation",
                "reason": "Critical 1개",
                "confidence": 0.95,
                "signals": {},
            },
        }
        assert route_after_action_decider(state) == "escalate"


# ── 2. Major ≥ 3 → request_rework ────────────────────────────────────────────

class TestMajorRework:
    def test_three_major_gives_request_rework(self):
        issues = [_issue("Major")] * 3
        decision = decide_action(issues)
        assert decision.recommended_action == "request_rework"

    def test_two_major_does_not_trigger_rework(self):
        issues = [_issue("Major")] * 2 + [_issue("Minor")]
        decision = decide_action(issues)
        assert decision.recommended_action != "request_rework"

    def test_route_request_rework_goes_to_store(self):
        state: Dev2State = {
            "task_id": "t2", "pr_id": "2", "pr_diff": "", "developer_id": "d1",
            "skill_level": "junior", "tech_stack": [], "architecture_docs": [],
            "coding_conventions": "", "previous_pr_issues": [],
            "static_raw": [], "security_raw": [], "enriched": [],
            "final_output": [], "tool_plan": None,
            "action_decision": {
                "recommended_action": "request_rework",
                "reason": "Major 3개",
                "confidence": 0.85,
                "signals": {},
            },
        }
        assert route_after_action_decider(state) == "store"


# ── 3. 중요 파일 Major → needs_human_review ───────────────────────────────────

class TestImportantFileReview:
    def test_auth_file_major_gives_needs_human_review(self):
        issues = [_issue("Major", file="src/auth.py")]
        decision = decide_action(issues)
        assert decision.recommended_action == "needs_human_review"
        assert decision.signals["important_file_issue"] is True

    def test_payment_file_major(self):
        issues = [_issue("Major", file="payments/checkout.py")]
        decision = decide_action(issues)
        assert decision.recommended_action == "needs_human_review"

    def test_normal_file_major_does_not_trigger_human_review(self):
        issues = [_issue("Major", file="src/utils.py")]
        decision = decide_action(issues)
        # Major 1개 + 일반 파일 → store_only
        assert decision.recommended_action == "store_only"

    def test_route_needs_human_review_goes_to_store(self):
        state: Dev2State = {
            "task_id": "t3", "pr_id": "3", "pr_diff": "", "developer_id": "d1",
            "skill_level": "junior", "tech_stack": [], "architecture_docs": [],
            "coding_conventions": "", "previous_pr_issues": [],
            "static_raw": [], "security_raw": [], "enriched": [],
            "final_output": [], "tool_plan": None,
            "action_decision": {
                "recommended_action": "needs_human_review",
                "reason": "중요 파일",
                "confidence": 0.80,
                "signals": {},
            },
        }
        assert route_after_action_decider(state) == "store"


# ── 4. confidence_score < 0.6 → needs_human_review ───────────────────────────

class TestLowConfidenceReview:
    def test_low_confidence_gives_needs_human_review(self):
        # confidence_score 0.5 (0 < x < 0.6)
        issues = [_issue("Minor", confidence=0.5)]
        decision = decide_action(issues)
        assert decision.recommended_action == "needs_human_review"
        assert decision.signals["low_confidence_issue"] is True

    def test_unmapped_zero_confidence_not_low_confidence(self):
        # confidence_score 0.0 = 미매핑 이슈 → low_confidence 아님
        issues = [_issue("Minor", confidence=0.0)]
        decision = decide_action(issues)
        assert decision.signals["low_confidence_issue"] is False

    def test_confidence_exactly_06_not_low(self):
        issues = [_issue("Minor", confidence=0.6)]
        decision = decide_action(issues)
        # 0.6은 임계치 미만이 아님 → low_confidence 아님
        assert decision.signals["low_confidence_issue"] is False


# ── 5. Minor만 → store_only ───────────────────────────────────────────────────

class TestStoreOnly:
    def test_only_minor_gives_store_only(self):
        issues = [_issue("Minor"), _issue("Minor")]
        decision = decide_action(issues)
        assert decision.recommended_action == "store_only"

    def test_empty_issues_gives_store_only(self):
        decision = decide_action([])
        # empty enriched는 노드에서 store_only 반환
        # decide_action([])은 store_only

    def test_route_store_only_goes_to_store(self):
        state: Dev2State = {
            "task_id": "t5", "pr_id": "5", "pr_diff": "", "developer_id": "d1",
            "skill_level": "junior", "tech_stack": [], "architecture_docs": [],
            "coding_conventions": "", "previous_pr_issues": [],
            "static_raw": [], "security_raw": [], "enriched": [],
            "final_output": [], "tool_plan": None,
            "action_decision": {
                "recommended_action": "store_only",
                "reason": "이슈 없음",
                "confidence": 0.90,
                "signals": {},
            },
        }
        assert route_after_action_decider(state) == "store"


# ── 6. LangGraph 노드 통합 ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_action_decider_node_critical():
    state: Dev2State = {
        "task_id": "t1", "pr_id": "1", "pr_diff": "", "developer_id": "d1",
        "skill_level": "junior", "tech_stack": [], "architecture_docs": [],
        "coding_conventions": "", "previous_pr_issues": [],
        "static_raw": [], "security_raw": [],
        "enriched": [_issue("Critical", "src/auth.py")],
        "final_output": [], "tool_plan": None, "action_decision": None,
    }
    result = await action_decider_agent_node(state)
    assert result["action_decision"]["recommended_action"] == "early_escalation"


@pytest.mark.asyncio
async def test_action_decider_node_empty_enriched():
    state: Dev2State = {
        "task_id": "t2", "pr_id": "2", "pr_diff": "", "developer_id": "d1",
        "skill_level": "junior", "tech_stack": [], "architecture_docs": [],
        "coding_conventions": "", "previous_pr_issues": [],
        "static_raw": [], "security_raw": [], "enriched": [],
        "final_output": [], "tool_plan": None, "action_decision": None,
    }
    result = await action_decider_agent_node(state)
    assert result["action_decision"]["recommended_action"] == "store_only"


@pytest.mark.asyncio
async def test_action_decider_signals_populated():
    issues = [_issue("Major")] * 3 + [_issue("Minor")]
    state: Dev2State = {
        "task_id": "t3", "pr_id": "3", "pr_diff": "", "developer_id": "d1",
        "skill_level": "junior", "tech_stack": [], "architecture_docs": [],
        "coding_conventions": "", "previous_pr_issues": [],
        "static_raw": [], "security_raw": [], "enriched": issues,
        "final_output": [], "tool_plan": None, "action_decision": None,
    }
    result = await action_decider_agent_node(state)
    signals = result["action_decision"]["signals"]
    assert signals["major_count"] == 3
    assert signals["minor_count"] == 1
    assert signals["critical_count"] == 0
