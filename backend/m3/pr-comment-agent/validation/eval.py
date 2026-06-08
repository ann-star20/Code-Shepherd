"""validation/eval.py — fixtures로 pr-comment-agent MVP를 E2E 검증한다.

사용법:
    py validation/eval.py               # 기본 fixtures 경로 사용
    py validation/eval.py path/out.json path/expected.json

검증 항목:
  1. verdict가 expected_verdict.json과 일치
  2. 이슈 개수(critical/major/minor/total)가 일치
  3. dry-run 파일 .dry_run_comments/PR-{n}.md 생성 확인
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# pr-comment-agent 루트 디렉토리를 sys.path에 추가 (직접 실행 시)
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from contracts import AgentOutput, Developer, ReviewReport
from main import run_review


_FIXTURES_DIR = Path(__file__).parent / "fixtures"
_DEFAULT_SAMPLE = _FIXTURES_DIR / "sample_outputs.json"
_DEFAULT_EXPECTED = _FIXTURES_DIR / "expected_verdict.json"
_DEFAULT_PR_URL = "https://github.com/acme/repo/pull/1"


def main(
    sample_outputs_path: str | None = None,
    expected_verdict_path: str | None = None,
    pr_url: str = _DEFAULT_PR_URL,
) -> ReviewReport:
    """fixtures를 읽어 run_review를 실행하고 결과를 검증한다.

    Args:
        sample_outputs_path: AgentOutput JSON 경로 (None이면 기본 fixtures 사용).
        expected_verdict_path: 예상 verdict JSON 경로 (None이면 기본 fixtures 사용).
        pr_url: GitHub PR URL (토큰 없으면 dry-run으로 처리됨).

    Returns:
        실행된 ReviewReport.

    Raises:
        AssertionError: verdict 또는 이슈 개수가 기대값과 다를 때.
    """
    sample_path = Path(sample_outputs_path) if sample_outputs_path else _DEFAULT_SAMPLE
    expected_path = Path(expected_verdict_path) if expected_verdict_path else _DEFAULT_EXPECTED

    # 1. fixtures 로드
    outputs_data = json.loads(sample_path.read_text(encoding="utf-8"))
    outputs = [AgentOutput(**entry) for entry in outputs_data]

    expected = json.loads(expected_path.read_text(encoding="utf-8"))

    # PR 번호를 URL에서 추출해 pr_url 조정
    if pr_url == _DEFAULT_PR_URL and outputs:
        pr_id = outputs[0].pr_id  # e.g. "PR-001"
        pr_num = pr_id.lstrip("PR-") or "1"
        pr_url = f"https://github.com/acme/repo/pull/{pr_num}"

    developer = Developer(name="eval-dev", skill_level="mid")

    # 2. 실행
    report = run_review(outputs, developer, pr_url)

    # 3. verdict 검증
    expected_verdict = expected["verdict"]
    assert report.verdict == expected_verdict, (
        f"verdict 불일치: got={report.verdict!r}  expected={expected_verdict!r}"
    )

    # 4. 이슈 개수 검증
    counts = expected["issue_count"]
    assert report.summary.critical == counts["critical"], (
        f"critical 불일치: got={report.summary.critical}  expected={counts['critical']}"
    )
    assert report.summary.major == counts["major"], (
        f"major 불일치: got={report.summary.major}  expected={counts['major']}"
    )
    assert report.summary.minor == counts["minor"], (
        f"minor 불일치: got={report.summary.minor}  expected={counts['minor']}"
    )
    total = report.summary.critical + report.summary.major + report.summary.minor
    assert total == counts["total"], (
        f"total 불일치: got={total}  expected={counts['total']}"
    )

    # 5. dry-run 파일 확인 (토큰 없을 때만)
    if report.gh_response and report.gh_response.get("mode") == "dry_run":
        dry_path = Path(report.gh_response["path"])
        assert dry_path.exists(), f"dry-run 파일이 생성되지 않음: {dry_path}"

    return report


if __name__ == "__main__":
    import io

    _buf = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    def _p(text: str) -> None:
        _buf.write(text + "\n")
        _buf.flush()

    sample_arg = sys.argv[1] if len(sys.argv) > 1 else None
    expected_arg = sys.argv[2] if len(sys.argv) > 2 else None

    _p("[eval] fixtures 로드 중...")
    report = main(sample_outputs_path=sample_arg, expected_verdict_path=expected_arg)

    _p(f"\n{'='*60}")
    _p(f"  verdict          : {report.verdict}")
    _p(f"  escalation_needed: {report.escalation_needed}")
    _p(f"  critical / major / minor : "
       f"{report.summary.critical} / {report.summary.major} / {report.summary.minor}")
    if report.gh_response:
        _p(f"  gh_response mode : {report.gh_response.get('mode')}")
        if "path" in report.gh_response:
            _p(f"  dry-run file     : {report.gh_response['path']}")
    _p(f"{'='*60}")
    _p("\n✅  PASS — 모든 검증 통과")
