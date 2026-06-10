"""Dev2와 컬럼 통일 — programming_language·framework·framework_version TDD.

requirements.txt(등)에서 파이썬 프레임워크와 버전을 파싱해 모든 이슈에 채운다.
레포 단위 정보라 test/performance 이슈 모두 동일하게 채움. LLM 없음(파일 파싱=사실).
"""
import textwrap
from pathlib import Path

from contracts import (AgentOutput, Developer, Dev3Input, Issue, RepoInfo,
                       SummaryCount)

SAMPLE_REPO = Path(__file__).parent / "fixtures" / "sample_repo"


def _repo(tmp_path, requirements: str | None) -> str:
    if requirements is not None:
        (tmp_path / "requirements.txt").write_text(
            textwrap.dedent(requirements), encoding="utf-8")
    return str(tmp_path)


# ─── 0) 모델 기본값 ───────────────────────────────────────────────────────────
def test_issue_framework_fields_default_empty():
    i = Issue(severity="Minor", file="x.py", message="m", rule_id="R")
    assert i.programming_language == ""
    assert i.framework == ""
    assert i.framework_version == ""


# ─── 1) django 버전 핀 파싱 ───────────────────────────────────────────────────
def test_detect_django_with_version(tmp_path):
    from enrich.framework import detect
    repo = _repo(tmp_path, """
        Django==4.2.1
        psycopg2-binary==2.9.9
    """)
    lang, fw, ver = detect(repo)
    assert lang == "python"
    assert fw == "django"
    assert ver == "4.2.1"


# ─── 2) flask, 버전 없음 ──────────────────────────────────────────────────────
def test_detect_flask_no_version(tmp_path):
    from enrich.framework import detect
    repo = _repo(tmp_path, "flask\nrequests>=2.0\n")
    lang, fw, ver = detect(repo)
    assert lang == "python"
    assert fw == "flask"
    assert ver == ""


# ─── 3) 여러 프레임워크 → 우선순위(django > fastapi > flask) ──────────────────
def test_detect_priority(tmp_path):
    from enrich.framework import detect
    repo = _repo(tmp_path, "flask==2.0\nfastapi==0.110.0\n")
    _, fw, ver = detect(repo)
    assert fw == "fastapi"
    assert ver == "0.110.0"


# ─── 4) requirements 없음 + .py 파일 없음 → 전부 빈 값 ──────────────────────────
def test_detect_no_requirements_no_py(tmp_path):
    from enrich.framework import detect
    lang, fw, ver = detect(str(tmp_path))
    assert (lang, fw, ver) == ("", "", "")


# ─── 4b) requirements 없지만 .py 파일 있음 → language=python (폴백) ───────────
def test_detect_no_requirements_but_py_file(tmp_path):
    from enrich.framework import detect
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    lang, fw, ver = detect(str(tmp_path))
    assert lang == "python"
    assert fw == ""    # 의존성 없으면 framework 빈값(정직)
    assert ver == ""   # 버전도 빈값


# ─── 4c) requirements 없고 .py 파일도 없음(다른 확장자) → 전부 빈 값 ─────────────
def test_detect_no_py_file_no_requirements(tmp_path):
    from enrich.framework import detect
    (tmp_path / "main.js").write_text("// js\n", encoding="utf-8")
    lang, fw, ver = detect(str(tmp_path))
    assert (lang, fw, ver) == ("", "", "")


# ─── 5) 프레임워크 없는 requirements → language만 python ──────────────────────
def test_detect_python_without_framework(tmp_path):
    from enrich.framework import detect
    repo = _repo(tmp_path, "requests==2.31.0\nnumpy\n")
    lang, fw, ver = detect(repo)
    assert lang == "python"
    assert fw == ""
    assert ver == ""


# ─── 6) augment_issues: 모든 이슈에 동일하게 채움 ─────────────────────────────
def test_augment_fills_all_issues(tmp_path):
    from enrich import framework
    repo = _repo(tmp_path, "Django==4.2.1\n")
    issues = [
        Issue(severity="Major", file="a.py", line=1, message="m", rule_id="PERF-001"),
        Issue(severity="Minor", file="b.py", line=None, message="m", rule_id="TEST-001"),
    ]
    framework.augment_issues(issues, repo)
    for i in issues:
        assert i.programming_language == "python"
        assert i.framework == "django"
        assert i.framework_version == "4.2.1"


# ─── 7) requirements 없으면 augment는 아무것도 안 함 ──────────────────────────
def test_augment_noop_without_requirements(tmp_path):
    from enrich import framework
    issue = Issue(severity="Minor", file="a.py", line=1, message="m", rule_id="PERF-001")
    framework.augment_issues([issue], str(tmp_path))
    assert issue.programming_language == ""
    assert issue.framework == ""


# ─── 8) main.run 끝까지 연결 — 모든 이슈에 programming_language 채워짐 ─────────
def test_main_run_populates_framework():
    from main import run
    diff = (SAMPLE_REPO.parent / "sample_pr.diff").read_text(encoding="utf-8")
    inp = Dev3Input(
        task_id="t", scan_id=1, pr_id="P", pr_diff=diff,
        repo=RepoInfo(clone_url="", commit_sha=""), developer=Developer(id="d"),
    )
    outputs = run(inp, str(SAMPLE_REPO))
    all_issues = [i for o in outputs for i in o.issues]
    assert all_issues, "이슈가 있어야 함"
    # sample_repo에 requirements.txt가 있으면 python 채워짐
    assert all(i.programming_language == "python" for i in all_issues)
