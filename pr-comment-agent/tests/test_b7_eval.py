"""B7: validation/eval.py + fixtures 검증."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch
import pytest

# validation 패키지를 임포트하기 위해 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

FIXTURES_DIR = Path(__file__).parent.parent / "validation" / "fixtures"
SAMPLE_OUTPUTS = FIXTURES_DIR / "sample_outputs.json"
EXPECTED_VERDICT = FIXTURES_DIR / "expected_verdict.json"
PR_URL = "https://github.com/acme/repo/pull/1"


# ── fixture 파일 존재 확인 ──────────────────────────────────────────────────────

class TestFixturesExist:
    def test_sample_outputs_file_exists(self):
        assert SAMPLE_OUTPUTS.exists(), "validation/fixtures/sample_outputs.json 파일이 없음"

    def test_expected_verdict_file_exists(self):
        assert EXPECTED_VERDICT.exists(), "validation/fixtures/expected_verdict.json 파일이 없음"

    def test_sample_outputs_has_four_entries(self):
        data = json.loads(SAMPLE_OUTPUTS.read_text(encoding="utf-8"))
        assert len(data) == 4, "sample_outputs.json에 AgentOutput 4개 필요"

    def test_all_same_scan_id(self):
        data = json.loads(SAMPLE_OUTPUTS.read_text(encoding="utf-8"))
        scan_ids = {entry["scan_id"] for entry in data}
        assert len(scan_ids) == 1, "모든 AgentOutput은 동일한 scan_id를 가져야 함"


# ── eval.main() 실행 결과 검증 ────────────────────────────────────────────────

class TestEvalMain:
    """validation.eval.main()이 fixtures를 읽고 run_review를 호출해 결과를 검증한다."""

    def test_eval_passes_without_exception(self, tmp_path, monkeypatch):
        """eval.main() 예외 없이 완료."""
        monkeypatch.chdir(tmp_path)
        import validation.eval as eval_mod
        eval_mod.main(
            sample_outputs_path=str(SAMPLE_OUTPUTS),
            expected_verdict_path=str(EXPECTED_VERDICT),
            pr_url=PR_URL,
        )

    def test_eval_verdict_matches_expected(self, tmp_path, monkeypatch):
        """집계된 verdict가 expected_verdict.json과 일치."""
        monkeypatch.chdir(tmp_path)
        import validation.eval as eval_mod
        report = eval_mod.main(
            sample_outputs_path=str(SAMPLE_OUTPUTS),
            expected_verdict_path=str(EXPECTED_VERDICT),
            pr_url=PR_URL,
        )
        expected = json.loads(EXPECTED_VERDICT.read_text(encoding="utf-8"))
        assert report.verdict == expected["verdict"]

    def test_eval_issue_counts_match_expected(self, tmp_path, monkeypatch):
        """이슈 개수가 expected_verdict.json의 issue_count와 일치."""
        monkeypatch.chdir(tmp_path)
        import validation.eval as eval_mod
        report = eval_mod.main(
            sample_outputs_path=str(SAMPLE_OUTPUTS),
            expected_verdict_path=str(EXPECTED_VERDICT),
            pr_url=PR_URL,
        )
        expected = json.loads(EXPECTED_VERDICT.read_text(encoding="utf-8"))
        counts = expected["issue_count"]
        assert report.summary.critical == counts["critical"]
        assert report.summary.major == counts["major"]
        assert report.summary.minor == counts["minor"]
        total_issues = report.summary.critical + report.summary.major + report.summary.minor
        assert total_issues == counts["total"]

    def test_dry_run_file_created(self, tmp_path, monkeypatch):
        """dry-run 모드 → .dry_run_comments/PR-{n}.md 파일 생성."""
        monkeypatch.chdir(tmp_path)
        import validation.eval as eval_mod
        eval_mod.main(
            sample_outputs_path=str(SAMPLE_OUTPUTS),
            expected_verdict_path=str(EXPECTED_VERDICT),
            pr_url=PR_URL,
        )
        dry_run_dir = tmp_path / ".dry_run_comments"
        assert dry_run_dir.exists(), ".dry_run_comments 디렉토리가 생성되지 않음"
        md_files = list(dry_run_dir.glob("*.md"))
        assert len(md_files) >= 1, ".dry_run_comments에 .md 파일이 없음"

    def test_dry_run_file_contains_verdict(self, tmp_path, monkeypatch):
        """생성된 dry-run 파일에 verdict 정보가 포함됨."""
        monkeypatch.chdir(tmp_path)
        import validation.eval as eval_mod
        report = eval_mod.main(
            sample_outputs_path=str(SAMPLE_OUTPUTS),
            expected_verdict_path=str(EXPECTED_VERDICT),
            pr_url=PR_URL,
        )
        dry_run_dir = tmp_path / ".dry_run_comments"
        md_files = list(dry_run_dir.glob("*.md"))
        if md_files:
            content = md_files[0].read_text(encoding="utf-8")
            assert report.verdict in content or "🤖" in content
