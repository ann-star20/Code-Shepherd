"""integration_demo.py — Dev3 → pr-comment-agent 통합 데모.

흐름:
  [1] test-performance-agent.main.run() 으로 fixture 실행 → Dev3 결과
  [2] aggregator: 이슈 집계 → verdict
  [3] llm_refiner (heuristic 모드): comment 생성
  [4] github_poster (dry-run): 파일 저장

두 에이전트가 형제 디렉토리에 있으므로 sys.path 교체 방식으로 import.
"""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path

# ── UTF-8 안전 출력 (Windows cp949 환경 대응) ────────────────────────────────
_buf = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def _p(text: str = "") -> None:
    _buf.write(text + "\n")
    _buf.flush()


def _banner(step: int, title: str) -> None:
    _p()
    _p("─" * 64)
    _p(f"  [{step}] {title}")
    _p("─" * 64)


# ── 경로 설정 ────────────────────────────────────────────────────────────────
_HERE = Path(__file__).parent.resolve()           # pr-comment-agent/
_DEV3_ROOT = (_HERE.parent / "test-performance-agent").resolve()
_FIXTURE_REPO = str(_DEV3_ROOT / "tests" / "fixtures" / "sample_repo")
_FIXTURE_DIFF = _DEV3_ROOT / "tests" / "fixtures" / "sample_pr.diff"


# ════════════════════════════════════════════════════════════════════════════
# [1] Dev3 실행 (test-performance-agent)
# ════════════════════════════════════════════════════════════════════════════
_banner(1, "Dev3 실행 (test-performance-agent)")

sys.path.insert(0, str(_DEV3_ROOT))

from contracts import Dev3Input, Developer as _Dev3Developer, RepoInfo  # noqa: E402
import main as _dev3_main                                                 # noqa: E402

pr_diff_text = _FIXTURE_DIFF.read_text(encoding="utf-8")
_dev3_input = Dev3Input(
    task_id="demo-integration-001",
    scan_id=999,
    pr_id="PR-999",
    pr_diff=pr_diff_text,
    repo=RepoInfo(clone_url="https://github.com/example/repo", commit_sha="demo"),
    developer=_Dev3Developer(id="demo_dev", skill_level="junior"),
)

_dev3_raw = _dev3_main.run(_dev3_input, _FIXTURE_REPO)

# 직렬화 (dict) — sys.modules 교체 전에 데이터 보존
_dev3_dicts = [o.model_dump() for o in _dev3_raw]

total_issues = sum(len(o.issues) for o in _dev3_raw)
cov_pct: float | None = None
for _o in _dev3_raw:
    if _o.metrics and "coverage_line" in _o.metrics:
        cov_pct = float(_o.metrics["coverage_line"])
cov_str = f"{cov_pct * 100:.0f}%" if cov_pct is not None else "N/A"

_p(f"  Dev3 실행: {total_issues} 이슈 검출 (커버리지 {cov_str})")
for _o in _dev3_raw:
    _p(f"    [{_o.agent}] critical={_o.summary.critical}  major={_o.summary.major}  minor={_o.summary.minor}")

# ── dev3 모듈 캐시 제거 → pr-comment-agent 모듈 활성화 ──────────────────────
_DEV3_MODULE_ROOTS = {
    "contracts", "main",
    "assemble", "config", "filter", "harness",
    "performance", "persist", "prepare",
    "test_verification", "tracing",
}
for _key in list(sys.modules.keys()):
    if _key.split(".")[0] in _DEV3_MODULE_ROOTS:
        del sys.modules[_key]

sys.path.pop(0)                          # dev3 경로 제거
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))


# ════════════════════════════════════════════════════════════════════════════
# [2] aggregator: 이슈 집계
# ════════════════════════════════════════════════════════════════════════════
_banner(2, "aggregator: 이슈 집계")

from contracts import AgentOutput, Developer  # pr-comment-agent 버전  # noqa: E402
from aggregator import aggregate               # noqa: E402

pr_outputs = [AgentOutput(**d) for d in _dev3_dicts]
combined_issues, verdict, _agg_summary = aggregate(pr_outputs)

_p(f"  aggregator: verdict={verdict}")
_p(f"  집계: critical={_agg_summary.critical}  major={_agg_summary.major}  minor={_agg_summary.minor}  total={len(combined_issues)}")


# ════════════════════════════════════════════════════════════════════════════
# [3] llm_refiner (heuristic 모드)
# ════════════════════════════════════════════════════════════════════════════
_banner(3, "llm_refiner (heuristic 모드): comment 생성")

from llm_refiner import _heuristic_refine  # noqa: E402

comment_md = _heuristic_refine(combined_issues, verdict)
first_line = comment_md.splitlines()[0][:72] if comment_md.strip() else "(empty)"
_p(f"  코멘트 생성 완료 ({len(comment_md)} chars)")
_p(f"  첫 줄: {first_line!r}")


# ════════════════════════════════════════════════════════════════════════════
# [4] github_poster (dry-run)
# ════════════════════════════════════════════════════════════════════════════
_banner(4, "github_poster (dry-run): 파일 저장 경로")

from github_poster import _dry_run  # noqa: E402

_pr_num_str = re.sub(r"\D", "", _dev3_input.pr_id)
_pr_num = int(_pr_num_str) if _pr_num_str else 999
gh_resp = _dry_run(_pr_num, comment_md)
_p(f"  dry-run 파일 저장: {gh_resp['path']}")


# ════════════════════════════════════════════════════════════════════════════
# 최종 요약 (ReviewReport 구조)
# ════════════════════════════════════════════════════════════════════════════
from contracts import ReviewReport  # noqa: E402

report = ReviewReport(
    verdict=verdict,
    issues=combined_issues,
    comment_md=comment_md,
    gh_response=gh_resp,
)

_p()
_p("=" * 64)
_p("  통합 데모 완료 — Dev3 → pr-comment-agent 한 흐름 검증")
_p("=" * 64)
_p(f"  verdict           : {report.verdict}")
_p(f"  escalation_needed : {report.escalation_needed}")
_p(f"  issues            : total={len(report.issues)}  critical={report.summary.critical}  major={report.summary.major}  minor={report.summary.minor}")
_p(f"  커버리지           : {cov_str}")
_p(f"  dry-run comment   : {report.gh_response['path']}")
_p("=" * 64)
