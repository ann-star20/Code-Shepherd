from dev2.schema import TaskPayload, AgentOutput, Issue, Summary, Dev2State


def test_task_payload():
    p = TaskPayload(
        task_id="uuid-001", pr_id="1",
        pr_diff="+++ b/src/auth.py",
        developer={"id": "dev-001", "skill_level": "junior", "tech_stack": ["python"]},
        context={"architecture_docs": ["chunk-001"], "coding_conventions": "PEP8",
                 "previous_pr_issues": ["N+1 쿼리"]}  # context 필드 포함 (CLAUDE.md §5-B)
    )
    assert p.developer.skill_level == "junior"
    assert p.context.previous_pr_issues == ["N+1 쿼리"]


def test_task_payload_context_defaults():
    # context 없이도 기본값으로 동작해야 함
    p = TaskPayload(
        task_id="uuid-002", pr_id="2",
        pr_diff="+++ b/src/app.py",
        developer={"id": "dev-001", "skill_level": "junior", "tech_stack": ["python"]}
    )
    assert p.context.architecture_docs == []
    assert p.context.previous_pr_issues == []


def test_dev2_state_extends_pr_review_state():
    # Dev2State는 PRReviewState 필드를 모두 포함해야 함 (CLAUDE.md §11)
    state: Dev2State = {
        "task_id": "uuid-001",
        "pr_id": "1",
        "pr_diff": "+++ b/src/auth.py",
        "developer_id": "dev-001",
        "static_raw": [],
        "security_raw": [],
        "enriched": [],
        "final_output": [],
    }
    assert state["task_id"] == "uuid-001"
    assert state["enriched"] == []


def test_issue_with_similar():
    issue = Issue(
        severity="Critical", line=42, file="src/auth.py",
        message="SQL 인젝션", rule_id="SEC-001",
        suggestion="파라미터화된 쿼리", similar_issues=[{"pr_id": "98", "similarity": 0.94}]
    )
    assert issue.similar_issues[0]["similarity"] == 0.94
