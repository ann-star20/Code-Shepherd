"""Dev2와 컬럼 통일 — Issue.github_id(작성자 GitHub 아이디) TDD.

github_id = PR 작성자 GitHub 아이디(문자). main.run에서 dev3_input.developer.id로
모든 이슈에 채운다(레포/PR 단위 정보). LLM 없음.
"""
from pathlib import Path

from contracts import Developer, Dev3Input, Issue, RepoInfo

SAMPLE_REPO = Path(__file__).parent / "fixtures" / "sample_repo"


def test_issue_github_id_default_empty():
    i = Issue(severity="Minor", file="x.py", message="m", rule_id="R")
    assert i.github_id == ""


def test_main_run_fills_github_id_from_developer():
    from main import run
    diff = (SAMPLE_REPO.parent / "sample_pr.diff").read_text(encoding="utf-8")
    inp = Dev3Input(
        task_id="t", scan_id=1, pr_id="P", pr_diff=diff,
        repo=RepoInfo(clone_url="", commit_sha=""),
        developer=Developer(id="kskt1234"),
    )
    outputs = run(inp, str(SAMPLE_REPO))
    all_issues = [i for o in outputs for i in o.issues]
    assert all_issues, "이슈가 있어야 함"
    assert all(i.github_id == "kskt1234" for i in all_issues)
