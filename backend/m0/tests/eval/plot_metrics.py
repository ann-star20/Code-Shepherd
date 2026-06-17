"""
KMS 파이프라인 성능 추이 시각화

metrics_history.json을 읽어 KPI 변화 추이를 4-panel 그래프로 생성한다.
터미널 비교 테이블도 함께 출력한다.

사용법:
    uv run python tests/eval/plot_metrics.py
    uv run python tests/eval/plot_metrics.py --show
    uv run python tests/eval/plot_metrics.py --table-only
    uv run python tests/eval/plot_metrics.py --output results/metrics_trend.png
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

EVAL_DIR = Path(__file__).parent
RESULTS_DIR = EVAL_DIR / "results"
DEFAULT_HISTORY = RESULTS_DIR / "metrics_history.json"
DEFAULT_OUTPUT  = RESULTS_DIR / "metrics_trend.png"

# KPI 패널 정의: (metrics 키, 표시 제목, y축 최대, 색상)
_PANELS = [
    ("maturity_score",     "Maturity Score (/100)",  100,  "tab:blue"),
    ("completion_rate",    "Completion Rate",          1.0, "tab:green"),
    ("tags_f1",            "Tags F1",                  1.0, "tab:orange"),
    ("entity_name_recall", "Entity Name Recall",       1.0, "tab:red"),
]

# 목표 기준선 (점선)
_TARGETS = {
    "completion_rate":    0.80,
    "tags_f1":            0.60,
    "entity_name_recall": 0.60,
}


def load_history(path: Path) -> list[dict]:
    if not path.exists():
        logger.error("파일 없음: %s  →  먼저 save_snapshot.py를 실행하세요", path)
        sys.exit(1)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not data:
        logger.error("metrics_history.json이 비어있습니다")
        sys.exit(1)
    return data


def print_comparison_table(history: list[dict]) -> None:
    """터미널 비교 테이블 출력."""
    KPI_COLS = [
        ("maturity_score",     "Maturity",   "{:>8.1f}"),
        ("completion_rate",    "Comp.Rate",  "{:>9.1%}"),
        ("tags_f1",            "Tags F1",    "{:>8.3f}"),
        ("entity_name_recall", "Ent.Recall", "{:>10.3f}"),
        ("quality_score",      "Quality",    "{:>8.3f}"),
    ]
    NA = "     N/A"

    col_w = max((len(h["label"]) for h in history), default=8) + 2
    header = (
        f"{'Label':<{col_w}}"
        + "".join(f"  {col[1]:>10}" for col in KPI_COLS)
        + "  CI Gate"
    )
    sep = "=" * len(header)

    print(f"\n{sep}")
    print(header)
    print("-" * len(header))
    for h in history:
        m = h["metrics"]
        row = f"{h['label']:<{col_w}}"
        for key, _, fmt in KPI_COLS:
            v = m.get(key)
            row += "  " + (fmt.format(v) if v is not None else NA).rjust(10)
        row += f"  {h.get('ci_gate', '?')}"
        print(row)
    print(f"{sep}\n")


def plot(history: list[dict], output_path: Path, show: bool) -> None:
    try:
        import matplotlib
        import matplotlib.pyplot as plt
        import matplotlib.ticker as mticker
    except ImportError:
        logger.error(
            "matplotlib 미설치\n"
            "  → uv add matplotlib --dev  후 재실행\n"
            "  → 또는: pip install matplotlib"
        )
        sys.exit(1)

    matplotlib.rcParams["font.family"] = "DejaVu Sans"

    labels = [h["label"] for h in history]
    x      = list(range(len(labels)))
    m_list = [h["metrics"] for h in history]

    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    fig.suptitle("KMS Pipeline Performance History", fontsize=14, fontweight="bold")

    for ax, (key, title, y_max, color) in zip(axes.flat, _PANELS):
        raw_vals = [m.get(key) for m in m_list]
        plot_vals = [v if v is not None else math.nan for v in raw_vals]

        ax.plot(x, plot_vals, marker="o", color=color, linewidth=2, markersize=6)
        ax.set_title(title, fontsize=11)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=8)
        ax.set_ylim(0, y_max * 1.12)
        ax.yaxis.set_major_formatter(
            mticker.PercentFormatter(xmax=1.0) if y_max == 1.0
            else mticker.ScalarFormatter()
        )
        ax.grid(True, alpha=0.3)

        if key in _TARGETS:
            tgt = _TARGETS[key]
            ax.axhline(
                tgt, color="gray", linestyle="--", alpha=0.6,
                label=f"target {tgt:.0%}",
            )
            ax.legend(fontsize=7)

        # 값 레이블
        for xi, val in zip(x, raw_vals):
            if val is None:
                continue
            label_text = f"{val:.1f}" if y_max == 100 else f"{val:.2f}"
            ax.annotate(
                label_text, (xi, val),
                textcoords="offset points", xytext=(0, 7),
                ha="center", fontsize=8,
            )

    fig.tight_layout()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    logger.info("그래프 저장: %s", output_path)

    if show:
        plt.show()
    else:
        plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="KMS 성능 추이 시각화")
    parser.add_argument(
        "--history",
        type=Path,
        default=DEFAULT_HISTORY,
        help="metrics_history.json 경로",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="그래프 저장 경로 (기본: results/metrics_trend.png)",
    )
    parser.add_argument("--show",       action="store_true", help="화면에 그래프 표시")
    parser.add_argument("--table-only", action="store_true", help="터미널 비교 테이블만 출력 (matplotlib 불필요)")
    args = parser.parse_args()

    history = load_history(args.history)
    print_comparison_table(history)

    if not args.table_only:
        plot(history, args.output, args.show)


if __name__ == "__main__":
    main()
