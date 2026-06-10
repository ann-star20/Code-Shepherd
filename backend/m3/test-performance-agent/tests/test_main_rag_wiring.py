"""main.run의 RAG 연결 — RAG_ENABLED일 때만 rag.augment 호출(기본 비활성).

기본 off: 평소·테스트에서 BGE-M3 로드·GCP 접속이 일어나지 않게(고립).
on(RAG_ENABLED=1): 탐지된 이슈에 사내 컨벤션을 검색해 rag_context를 채움.
"""
from unittest.mock import patch

import main
from contracts import Developer, Dev3Input, Issue, RepoInfo


def _inp() -> Dev3Input:
    return Dev3Input(
        task_id="t", scan_id=1, pr_id="P",
        pr_diff=("diff --git a/src/posts.py b/src/posts.py\n"
                 "+++ b/src/posts.py\n@@ -0,0 +1 @@\n+x=1\n"),
        repo=RepoInfo(clone_url="", commit_sha=""), developer=Developer(id="d"),
    )


def _detector_patches():
    n1 = Issue(severity="Major", file="src/posts.py", line=1,
               message="N+1", rule_id="PERF-002")
    return [
        patch("main.coverage.measure", return_value=([], None)),
        patch("main.missing_funcs.detect", return_value=[]),
        patch("main.nplus1.detect", return_value=[n1]),
        patch("main.complexity.detect", return_value=[]),
    ]


def _run(tmp_path):
    ps = _detector_patches()
    for p in ps:
        p.start()
    try:
        return main.run(_inp(), str(tmp_path))
    finally:
        for p in ps:
            p.stop()


def test_rag_augment_called_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("RAG_ENABLED", "1")
    calls = {"n": 0}
    monkeypatch.setattr(main.rag_augment, "augment_issues",
                        lambda issues: calls.__setitem__("n", calls["n"] + 1))
    _run(tmp_path)
    assert calls["n"] >= 1


def test_rag_augment_skipped_when_disabled(tmp_path, monkeypatch):
    monkeypatch.delenv("RAG_ENABLED", raising=False)
    calls = {"n": 0}
    monkeypatch.setattr(main.rag_augment, "augment_issues",
                        lambda issues: calls.__setitem__("n", 1))
    _run(tmp_path)
    assert calls["n"] == 0


def test_rag_off_without_explicit_env(tmp_path, monkeypatch):
    """conftest _rag_off autouse 가 RAG_ENABLED 을 unset 해두므로
    테스트에서 명시적으로 setenv 하지 않으면 augment 가 호출되지 않는다.

    docker-compose 에 RAG_ENABLED=1 이 있어도 이 보호가 유지돼야
    단위테스트가 BGE-M3·GCP 를 실제로 때리지 않는다.
    """
    # conftest _rag_off autouse 이미 unset → 여기서 추가 monkeypatch 없음
    calls = {"n": 0}
    monkeypatch.setattr(main.rag_augment, "augment_issues",
                        lambda issues: calls.__setitem__("n", 1))
    _run(tmp_path)
    assert calls["n"] == 0
