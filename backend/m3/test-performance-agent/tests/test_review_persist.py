"""persist.save_review / get_review — m3 /review 결과 저장·조회 TDD.

로컬 SQLite(DB_PATH)를 임시 파일로 격리해 검증한다.
- 저장 후 (owner, repo, pr_number) 키로 {verdict, comment, issues} 복원.
- 같은 키 재저장 → UPSERT(덮어쓰기).
- 없는 키 조회 → None(빈 결과).
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import persist as p  # noqa: E402


class TestReviewPersist:
    def setup_method(self):
        self._tf = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._db_path = self._tf.name
        self._tf.close()
        self._orig = p.DB_PATH
        p.DB_PATH = self._db_path

    def teardown_method(self):
        p.DB_PATH = self._orig
        try:
            os.remove(self._db_path)
        except OSError:
            pass

    def test_save_then_get_roundtrip(self):
        issues = [{"severity": "Critical", "rule_id": "SEC-001", "file": "a.py", "line": 3}]
        p.save_review("octocat", "hello", 5, "escalate", "## 코멘트", issues)

        got = p.get_review("octocat", "hello", 5)
        assert got is not None
        assert got["verdict"] == "escalate"
        assert got["comment"] == "## 코멘트"
        assert got["issues"] == issues

    def test_save_is_upsert(self):
        p.save_review("octocat", "hello", 5, "rework", "v1", [])
        p.save_review("octocat", "hello", 5, "lgtm", "v2", [{"rule_id": "X"}])

        got = p.get_review("octocat", "hello", 5)
        assert got["verdict"] == "lgtm"      # 최신 값으로 덮어씀
        assert got["comment"] == "v2"
        assert got["issues"] == [{"rule_id": "X"}]

    def test_get_missing_returns_none(self):
        assert p.get_review("nobody", "nope", 999) is None
