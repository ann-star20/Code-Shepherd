"""
KMS 파이프라인 평가 스냅샷 저장 스크립트

run_eval.py가 생성한 report.json을 읽어 metrics_history.json에 누적 저장한다.
동시에 results/{label}_metrics.json으로 포트폴리오용 독립 파일도 저장한다.

사용법:
    uv run python tests/eval/save_snapshot.py --label baseline
    uv run python tests/eval/save_snapshot.py --label improved_v1 --note "Stage 2 수정"
    uv run python tests/eval/save_snapshot.py --label improved_v2 --overwrite
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

EVAL_DIR = Path(__file__).parent
RESULTS_DIR = EVAL_DIR / "results"
HISTORY_PATH = RESULTS_DIR / "metrics_history.json"


def _git_info() -> dict:
    def _run(cmd: list[str]) -> str:
        try:
            return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()
        except Exception:
            return ""

    return {
        "commit_hash":    _run(["git", "rev-parse", "--short", "HEAD"]),
        "commit_full":    _run(["git", "rev-parse", "HEAD"]),
        "branch":         _run(["git", "branch", "--show-current"]),
        "commit_message": _run(["git", "log", "-1", "--pretty=%s"]),
    }


def _extract_metrics(report: dict) -> dict:
    """report.json에서 핵심 KPI를 평탄화해 반환한다."""
    auto    = report.get("automation", {})
    acc     = report.get("accuracy", {})
    timing  = report.get("reliability", {}).get("timing", {})

    return {
        "maturity_score":         report.get("maturity_score"),
        "total_documents":        auto.get("total_documents"),
        "stored":                 auto.get("stored"),
        "hitl_pending":           auto.get("hitl_pending"),
        "error_or_timeout":       auto.get("error_or_timeout"),
        "completion_rate":        auto.get("completion_rate"),
        "hitl_rate":              auto.get("hitl_rate"),
        "error_rate":             auto.get("error_rate"),
        "title_accuracy":         acc.get("title_accuracy"),
        "category_accuracy":      acc.get("category_accuracy"),
        "tags_f1":                acc.get("avg_tags_f1"),
        "entity_name_recall":     acc.get("avg_entity_name_recall"),
        "entity_partial_score":   acc.get("avg_entity_partial_score"),
        "quality_score":          acc.get("avg_quality_score"),
        "avg_processing_time_ms": timing.get("avg_ms"),
    }


def load_history() -> list[dict]:
    if HISTORY_PATH.exists():
        return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    return []


def save_history(history: list[dict]) -> None:
    HISTORY_PATH.write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_snapshot(
    label: str,
    report: dict,
    note: str,
    dataset_version: str,
) -> dict:
    git = _git_info()
    return {
        "label":           label,
        "evaluation_date": report.get("timestamp", datetime.now().isoformat()),
        "saved_at":        datetime.now().isoformat(),
        "git_commit_hash": git["commit_hash"],
        "git_commit_full": git["commit_full"],
        "git_branch":      git["branch"],
        "git_message":     git["commit_message"],
        "dataset_version": dataset_version,
        "note":            note,
        "ci_gate":         report.get("ci_gate", {}).get("overall", "UNKNOWN"),
        "metrics":         _extract_metrics(report),
        "status_breakdown": report.get("automation", {}).get("status_breakdown", {}),
    }


def _print_summary(snapshot: dict) -> None:
    m = snapshot["metrics"]

    def _fmt(key: str, fmt: str = ".3f") -> str:
        v = m.get(key)
        return "N/A" if v is None else format(v, fmt)

    def _p(text: str) -> None:
        try:
            print(text)
        except UnicodeEncodeError:
            print(text.encode("ascii", errors="replace").decode())

    sep = "=" * 52
    _p(f"\n{sep}")
    _p(f"  Snapshot saved: {snapshot['label']}")
    _p(f"  Commit: {snapshot['git_commit_hash']}  ({snapshot['git_message']})")
    _p(f"  Branch: {snapshot['git_branch']}")
    if snapshot["note"]:
        _p(f"  Note: {snapshot['note']}")
    _p(sep)
    _p(f"  Maturity Score:  {_fmt('maturity_score', '.1f')} / 100")
    _p(f"  Completion Rate: {_fmt('completion_rate', '.1%')}")
    _p(f"  HITL Rate:       {_fmt('hitl_rate', '.1%')}")
    _p(f"  Tags F1:         {_fmt('tags_f1')}")
    _p(f"  Entity Recall:   {_fmt('entity_name_recall')}")
    _p(f"  Quality Score:   {_fmt('quality_score')}")
    _p(f"  CI Gate:         {snapshot['ci_gate']}")
    _p(f"{sep}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="평가 스냅샷 저장")
    parser.add_argument(
        "--label",
        required=True,
        help="스냅샷 레이블 (예: baseline, improved_v1, improved_v2)",
    )
    parser.add_argument("--note", default="", help="변경 내용 메모")
    parser.add_argument(
        "--report",
        type=Path,
        default=RESULTS_DIR / "report.json",
        help="run_eval.py 출력 JSON 경로 (기본: results/report.json)",
    )
    parser.add_argument("--dataset-version", default="v1", help="데이터셋 버전")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="동일 label이 있으면 교체 (기본: 새 항목 추가)",
    )
    args = parser.parse_args()

    if not args.report.exists():
        logger.error(
            "report.json 없음: %s  →  먼저 run_eval.py를 실행하세요",
            args.report,
        )
        sys.exit(1)

    report   = json.loads(args.report.read_text(encoding="utf-8"))
    snapshot = build_snapshot(args.label, report, args.note, args.dataset_version)

    # 누적 히스토리 업데이트
    history = load_history()
    if args.overwrite:
        removed = sum(1 for h in history if h.get("label") == args.label)
        history = [h for h in history if h.get("label") != args.label]
        if removed:
            logger.info("기존 '%s' 항목 %d개 교체", args.label, removed)
    history.append(snapshot)
    save_history(history)
    logger.info("metrics_history.json 업데이트 → 총 %d개 항목", len(history))

    # 포트폴리오용 독립 파일 저장
    standalone = RESULTS_DIR / f"{args.label}_metrics.json"
    standalone.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("독립 파일 저장: %s", standalone)

    _print_summary(snapshot)


if __name__ == "__main__":
    main()
