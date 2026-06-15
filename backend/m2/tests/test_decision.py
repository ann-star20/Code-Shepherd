"""decision.py 단위 테스트 — 분석 라우팅 판단."""

from app.decision import decide

PY_DIFF = """diff --git a/src/db.py b/src/db.py
--- a/src/db.py
+++ b/src/db.py
@@ -0,0 +1,2 @@
+def add(a, b):
+    return a + b
"""

PY_SECURITY_DIFF = """diff --git a/src/auth.py b/src/auth.py
--- a/src/auth.py
+++ b/src/auth.py
@@ -0,0 +1,2 @@
+password = "hunter2"
+token = get_secret()
"""

MD_ONLY_DIFF = """diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -0,0 +1,1 @@
+# Hello
"""

DEP_ONLY_DIFF = """diff --git a/requirements.txt b/requirements.txt
--- a/requirements.txt
+++ b/requirements.txt
@@ -0,0 +1,1 @@
+requests==2.0.0
"""


def test_python_change_needs_static_and_security():
    d = decide(PY_DIFF)
    assert d.skip is False
    assert d.needs_static is True
    assert d.needs_security is True
    assert "src/db.py" in d.supported_files


def test_security_keyword_sets_signal():
    d = decide(PY_SECURITY_DIFF)
    assert d.needs_security is True
    assert d.security_signal is True


def test_docs_only_is_skip():
    d = decide(MD_ONLY_DIFF)
    assert d.skip is True
    assert d.needs_static is False
    assert d.needs_security is False


def test_dependency_only_is_skip_with_security_signal():
    # 의존성 파일만 변경 → 스캔할 소스가 없어 skip이지만 보안 신호는 기록된다.
    d = decide(DEP_ONLY_DIFF)
    assert d.skip is True
    assert d.security_signal is True


def test_empty_diff_is_skip():
    d = decide("")
    assert d.skip is True
