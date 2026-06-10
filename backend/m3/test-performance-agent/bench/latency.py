"""bench/latency.py — 단계별 소요 시간 벤치마크.

실행:
    # m3 컨테이너 내부에서
    uv run python bench/latency.py

결과:
    bench/리포트.md  에 markdown 표 저장.

설계:
- LatencyCollector + @instrument를 통해 각 파이프라인 단계 ms 수집.
- sandbox(Docker pytest)는 사전 fixture coverage.json 활용 → 측정 생략(명시).
- PR 크기: tiny/small/medium/large/xlarge 5종 × N회(기본 3회) = 15+회 실행.
- 첫 실행(cold) vs 2회 이후(warm) 분리.
- RAG_ENABLED=0(기본) → rag 행은 (off).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

# ── 경로 설정 ──────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent  # test-performance-agent/
_BENCH = _HERE

if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_BENCH) not in sys.path:
    sys.path.insert(0, str(_BENCH))

from contracts import Developer, Dev3Input, RepoInfo
from harness import LatencyCollector
from collector import build_stats, format_report_table, split_cold_warm
import main as dev3_main

# ── 샘플 diff 생성 ──────────────────────────────────────────────────────────

_BASE_DIFF = """diff --git a/src/posts.py b/src/posts.py
new file mode 100644
index 0000000..1111111
--- /dev/null
+++ b/src/posts.py
@@ -0,0 +1,22 @@
+\"\"\"샘플 PR 코드 - 의도적 결함 포함 (N+1, O(n^2)).\"\"\"\n+
+
+def get_posts(post_ids):
+    posts = []
+    for pid in post_ids:
+        post = db.query(f"SELECT * FROM posts WHERE id={pid}")
+        posts.append(post)
+    return posts
+
+
+def calc_discount(price, rate):
+    return price * (1 - rate)
+
+
+def find_dups(items):
+    result = []
+    for i in items:
+        for j in items:
+            if i == j:
+                result.append(i)
+    return result
"""


def _make_diff(size: str) -> str:
    """크기별 PR diff 생성. 실제 sample_repo 파일 경로를 사용."""
    base = _BASE_DIFF
    if size == "tiny":
        return (
            "diff --git a/src/posts.py b/src/posts.py\n"
            "+++ b/src/posts.py\n"
            "@@ -0,0 +1,3 @@\n"
            "+def add(a, b):\n"
            "+    return a + b\n"
            "+\n"
        )
    elif size == "small":
        return base
    elif size == "medium":
        extra = "\n".join(
            f"+    item_{i} = process(data[{i}])" for i in range(20)
        )
        return base + (
            "\ndiff --git a/src/old_utils.py b/src/old_utils.py\n"
            "+++ b/src/old_utils.py\n"
            "@@ -0,0 +1,22 @@\n"
            "+def load_all(db):\n"
            "+    items = []\n"
            "+    for row in db.fetchall():\n"
            "+        items.append(row)\n"
            "+    return items\n"
            + extra + "\n"
        )
    elif size == "large":
        funcs = "\n".join(
            f"+def func_{i}(x):\n+    for a in x:\n+        for b in x:\n+            pass\n"
            for i in range(5)
        )
        return base + (
            "\ndiff --git a/src/old_utils.py b/src/old_utils.py\n"
            "+++ b/src/old_utils.py\n"
            "@@ -0,0 +1,42 @@\n"
            + funcs
        )
    else:  # xlarge
        funcs = "\n".join(
            f"+def nested_{i}(x):\n+    for a in x:\n+        for b in x:\n+            for c in x:\n+                pass\n"
            for i in range(8)
        )
        return base + (
            "\ndiff --git a/src/old_utils.py b/src/old_utils.py\n"
            "+++ b/src/old_utils.py\n"
            "@@ -0,0 +1,70 @@\n"
            + funcs
        )


PR_SIZES = ["tiny", "small", "medium", "large", "xlarge"]
PR_LABELS = {
    "tiny": "fixtures/tiny (3줄)",
    "small": "fixtures/small (22줄, N+1+복잡도)",
    "medium": "fixtures/medium (45줄, 2파일)",
    "large": "fixtures/large (65줄, 2파일·중첩루프)",
    "xlarge": "fixtures/xlarge (90줄, 2파일·3중루프)",
}


def _make_input(pr_id: str, diff: str) -> Dev3Input:
    return Dev3Input(
        task_id=f"bench-{pr_id}",
        scan_id=0,
        pr_id=pr_id,
        pr_diff=diff,
        repo=RepoInfo(clone_url="https://github.com/example/repo", commit_sha="bench"),
        developer=Developer(id="bench_runner"),
    )


# ── 단일 실행 ────────────────────────────────────────────────────────────────

def _run_once(
    pr_id: str, diff: str, repo_path: str
) -> dict[str, list[float]]:
    """파이프라인 1회 실행 → {stage: [ms]} (LatencyCollector 결과)."""
    inp = _make_input(pr_id, diff)
    with LatencyCollector() as col:
        try:
            dev3_main.run(inp, repo_path)
        except Exception as e:
            print(f"  [warn] {pr_id} 실행 예외(무시): {type(e).__name__}: {e}")
    return col.to_dict()


# ── 메인 벤치마크 ────────────────────────────────────────────────────────────

def run_benchmark(
    repo_path: str,
    n_repeats: int = 3,
) -> tuple[list[dict[str, list[float]]], list[str]]:
    """모든 PR × n_repeats 회 실행 → (all_runs_flat, pr_labels)."""
    all_runs: list[dict[str, list[float]]] = []
    pr_labels: list[str] = []

    for size in PR_SIZES:
        diff = _make_diff(size)
        label = PR_LABELS[size]
        for rep in range(n_repeats):
            pr_id = f"{size}-rep{rep+1}"
            print(f"  측정 {pr_id} ...", flush=True)
            run_result = _run_once(pr_id, diff, repo_path)
            all_runs.append(run_result)
        pr_labels.append(label)

    return all_runs, pr_labels


def _merge_runs(runs: list[dict[str, list[float]]]) -> dict[str, list[float]]:
    """여러 실행의 timings를 하나의 {stage: [all_ms]} 딕셔너리로 합친다."""
    merged: dict[str, list[float]] = {}
    for run in runs:
        for stage, ms_list in run.items():
            merged.setdefault(stage, []).extend(ms_list)
    return merged


# ── 리포트 생성 ──────────────────────────────────────────────────────────────

def generate_report(
    all_runs: list[dict[str, list[float]]],
    pr_labels: list[str],
    n_repeats: int,
    output_path: Path,
) -> str:
    """all_runs → markdown 리포트 생성 및 파일 저장."""
    total = len(all_runs)
    cold_run, warm_runs = split_cold_warm(all_runs)

    # cold: 첫 번째 실행만
    cold_timings = cold_run  # {stage: [ms]}
    cold_stats = build_stats(cold_timings)

    # warm: 나머지 실행들
    warm_merged = _merge_runs(warm_runs)
    warm_stats = build_stats(warm_merged)

    # combined (전체)
    all_merged = _merge_runs(all_runs)
    combined_stats = build_stats(all_merged)

    rag_enabled = bool(os.getenv("RAG_ENABLED"))
    env_note = "m3 컨테이너 내 직접 실행 (sandbox=fixture coverage.json 사용)"

    report_lines = [
        "# m3 파이프라인 단계별 소요 시간 벤치마크",
        "",
        f"생성일: {_today()}",
        f"환경: {env_note}",
        f"sandbox(Docker pytest): fixture coverage.json 사용 — 실제 Docker sandbox 미실행(생략)",
        f"RAG: {'on' if rag_enabled else 'off (RAG_ENABLED 미설정)'}",
        "",
        f"**측정 PR ({len(pr_labels)}종 × {n_repeats}회 = {total}회)**",
        "",
    ]
    for i, label in enumerate(pr_labels):
        report_lines.append(f"- PR{i+1}: {label}")
    report_lines.append("")

    # combined 표
    report_lines.append(
        format_report_table(
            combined_stats,
            n=total,
            prs=[f"PR{i+1}" for i in range(len(pr_labels))],
            rag_enabled=rag_enabled,
            cold_stats=cold_stats,
            warm_stats=warm_stats,
            env_note=env_note,
        )
    )

    report_lines.append("")
    report_lines.append("## 한계")
    report_lines.append("")
    report_lines.append("- **sandbox**: Docker-in-Docker 격리 실행은 미포함. 실제 환경에서는 sandbox 단계가 가장 큰 병목일 가능성 있음.")
    report_lines.append("- **LLM(code_context)**: LLM 호출은 `USE_MOCK_LLM` 또는 키 상태에 따라 달라짐. 키 없는 환경에서는 heuristic fallback.")
    report_lines.append("- **GitHub post/persist**: 이 벤치마크에서는 pr-comment-agent(refine/post/persist)를 포함하지 않음.")
    report_lines.append("- **clone**: GitHub 실 clone은 별도 측정 필요 (네트워크 가변).")
    report_lines.append(f"- 표본 N={total} (크기별 {n_repeats}회), 통계적 유의성 낮음 — 추세 참고용.")

    report_md = "\n".join(report_lines)
    output_path.write_text(report_md, encoding="utf-8")
    return report_md


def _today() -> str:
    import datetime
    return datetime.date.today().isoformat()


# ── 진입점 ───────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="m3 파이프라인 단계별 소요 시간 벤치마크")
    parser.add_argument(
        "--repo-path",
        default=str(_ROOT / "tests" / "fixtures" / "sample_repo"),
        help="분석 대상 레포 경로 (기본: tests/fixtures/sample_repo)",
    )
    parser.add_argument(
        "--n", type=int, default=3,
        help="PR당 반복 횟수 (기본: 3)",
    )
    parser.add_argument(
        "--output", default=str(_BENCH / "리포트.md"),
        help="리포트 저장 경로",
    )
    args = parser.parse_args()

    repo_path = args.repo_path
    n_repeats = args.n
    output_path = Path(args.output)

    print(f"[bench] 레포: {repo_path}")
    print(f"[bench] PR 크기: {PR_SIZES}  반복: {n_repeats}회")
    print(f"[bench] 총 실행: {len(PR_SIZES) * n_repeats}회")
    print("")

    all_runs, pr_labels = run_benchmark(repo_path, n_repeats=n_repeats)

    print("")
    print(f"[bench] 리포트 생성 중 → {output_path}")
    report = generate_report(all_runs, pr_labels, n_repeats, output_path)

    print("")
    print(report)
    print(f"\n[bench] 완료. 저장: {output_path}")


if __name__ == "__main__":
    main()
