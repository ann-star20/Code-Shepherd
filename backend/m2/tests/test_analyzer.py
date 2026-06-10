"""analyzer 단위 테스트 — 도구 출력 매핑을 subprocess Mock으로 검증.

실제 pylint/bandit 설치 없이 통과해야 한다(루트 가이드 §13).
"""

import json
from types import SimpleNamespace
from unittest.mock import patch

from app import analyzer
from app.analyzer import _parse_diff, analyze

PY_DIFF = """diff --git a/src/db.py b/src/db.py
--- a/src/db.py
+++ b/src/db.py
@@ -0,0 +1,3 @@
+def q(name):
+    return f"SELECT * FROM users WHERE name = '{name}'"
+
"""


def _fake_proc(stdout: str):
    return SimpleNamespace(stdout=stdout, stderr="", returncode=1)


def test_parse_diff_reconstructs_post_image():
    files = _parse_diff(PY_DIFF)
    assert "src/db.py" in files
    content = files["src/db.py"]
    assert "def q(name):" in content
    assert "SELECT * FROM users" in content


def test_parse_diff_skips_deleted_file():
    deleted = (
        "diff --git a/gone.py b/gone.py\n"
        "--- a/gone.py\n"
        "+++ /dev/null\n"
        "@@ -1 +0,0 @@\n"
        "-print('x')\n"
    )
    assert _parse_diff(deleted) == {}


def test_empty_diff_returns_empty_result():
    issues, summary, ms = analyze("", "static_analysis")
    assert issues == []
    assert summary.critical == summary.major == summary.minor == 0
    assert ms >= 0


def test_security_maps_bandit_output_and_summary():
    bandit_json = json.dumps(
        {
            "results": [
                {
                    "issue_severity": "HIGH",
                    "line_number": 2,
                    "filename": "src/db.py",
                    "issue_text": "Possible SQL injection",
                    "test_id": "B608",
                    "more_info": "https://bandit.example/B608",
                }
            ]
        }
    )

    def fake_run(cmd, cwd, capture_output, text, timeout):
        if "bandit" in cmd:
            return _fake_proc(bandit_json)
        return _fake_proc("")  # semgrep 등 → 빈 출력

    with patch.object(analyzer.subprocess, "run", side_effect=fake_run), patch.object(
        analyzer, "_resolve_semgrep", return_value=["semgrep"]
    ):
        issues, summary, _ = analyze(PY_DIFF, "security_scan")

    assert len(issues) == 1
    issue = issues[0]
    assert issue.severity == "Critical"
    assert issue.rule_id == "SEC-B608"
    assert issue.file == "src/db.py"
    assert summary.critical == 1


def test_static_maps_pylint_output():
    pylint_json = json.dumps(
        [
            {
                "type": "error",
                "line": 1,
                "path": "src/db.py",
                "message": "undefined name",
                "message-id": "E0602",
                "symbol": "undefined-variable",
            }
        ]
    )

    def fake_run(cmd, cwd, capture_output, text, timeout):
        if "pylint" in cmd:
            return _fake_proc(pylint_json)
        return _fake_proc("")  # radon → 빈 출력

    with patch.object(analyzer.subprocess, "run", side_effect=fake_run):
        issues, summary, _ = analyze(PY_DIFF, "static_analysis")

    assert any(i.rule_id == "SA-E0602" and i.severity == "Critical" for i in issues)
    assert summary.critical == 1


def test_missing_tool_is_graceful_skip():
    with patch.object(analyzer.subprocess, "run", side_effect=FileNotFoundError):
        issues, summary, _ = analyze(PY_DIFF, "static_analysis")
    assert issues == []
    assert summary.major == 0
