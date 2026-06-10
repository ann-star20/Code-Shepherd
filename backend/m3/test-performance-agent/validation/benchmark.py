"""SESSION 8B — 탐지 정확도 벤치마크: 양성+음성 라벨셋 → rule별 P/R/F1.

1커맨드 재실행:
    # m3 컨테이너 안, 결정성 위해 무키·RAG off 권장
    RAG_ENABLED= GOOGLE_API_KEY= uv run python validation/benchmark.py

산출:
    validation/benchmark_report.md  (발표자료 §2-5 탐지 성능평가 표)

원칙(정직):
  - 라벨(정답)은 사람이 **rule 정의로부터** 확정한 값. 탐지기 출력으로 자동생성하지 않음(순환 금지).
  - 매칭은 기존 eval 과 동일한 (rule_id, file) 멀티셋(line·severity 는 식별자 아님).
  - 음성 케이스(expected 0)에서 나오는 출력은 FP 로 잡혀 precision 하락 → 휴리스틱 약점이 정직하게 드러남.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent  # test-performance-agent/
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import main as dev3_main  # noqa: E402
from contracts import Developer, Dev3Input, RepoInfo  # noqa: E402
from validation.eval import evaluate_prf  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# 라벨셋 — 사람이 rule 정의로 확정한 정답(양성 3 + 음성 2 = 5케이스, 6규칙 전부 커버)
# ─────────────────────────────────────────────────────────────────────────────

def _exp(tv: list[tuple[str, str]], perf: list[tuple[str, str]]) -> dict:
    return {
        "test_verification": {
            "expected_issues": [{"rule_id": r, "file": f} for r, f in tv]
        },
        "performance": {
            "expected_issues": [{"rule_id": r, "file": f} for r, f in perf]
        },
    }


CASES: list[dict] = [
    {
        # 양성 — 실 pytest 로 만든 coverage.json 보유(신뢰 가능). 6규칙 중 5개 동시.
        "name": "pos_coverage_sample",
        "kind": "positive",
        "repo": "tests/fixtures/sample_repo",
        "diff_file": "tests/fixtures/sample_pr.diff",
        "expected": _exp(
            tv=[
                ("TEST-001", "(전체)"),          # 라인 커버리지 20% < 80%
                ("TEST-004", "src/posts.py"),     # get_posts 미테스트
                ("TEST-004", "src/posts.py"),     # find_dups 미테스트
                ("TEST-003", "src/posts.py"),     # get_posts(post_ids) 엣지 누락
                ("TEST-003", "src/posts.py"),     # calc_discount(price,rate) 엣지 누락
                ("TEST-003", "src/posts.py"),     # find_dups(items) 엣지 누락
            ],
            perf=[
                ("PERF-002", "src/posts.py"),     # get_posts 루프 안 db.query (N+1)
                ("PERF-001", "src/posts.py"),     # find_dups 2중 중첩루프
            ],
        ),
    },
    {
        # 양성 — N+1 + 3중루프, 인자명 때문에 TEST-003 동반.
        "name": "pos_perf_nplus1_complexity",
        "kind": "positive",
        "repo": "tests/fixtures/labelset/perf_case",
        "files": ["src/app.py"],
        "expected": _exp(
            tv=[
                ("TEST-003", "src/app.py"),       # get_users(user_ids)
                ("TEST-003", "src/app.py"),       # find_triples(items)
            ],
            perf=[
                ("PERF-002", "src/app.py"),       # get_users 루프 안 db.query
                ("PERF-001", "src/app.py"),       # find_triples 3중 중첩루프
            ],
        ),
    },
    {
        # 양성 — 메모리 누수 2패턴(PERF-003만 격리, 인자명 안전).
        "name": "pos_memleak",
        "kind": "positive",
        "repo": "tests/fixtures/labelset/memleak_case",
        "files": ["src/cache.py"],
        "expected": _exp(
            tv=[],
            perf=[
                ("PERF-003", "src/cache.py"),     # 전역 EVENTS append
                ("PERF-003", "src/cache.py"),     # open() 단독 호출
            ],
        ),
    },
    {
        # 음성 — 진짜 깨끗한 코드. 6탐지기 모두 0건이어야 함.
        "name": "neg_clean",
        "kind": "negative",
        "repo": "tests/fixtures/labelset/clean_case",
        "files": ["src/calc.py"],
        "expected": _exp(tv=[], perf=[]),
    },
    {
        # 음성 — 엣지케이스 *이미 처리*. 정답 0건이나 휴리스틱이 TEST-003 오탐(FP) → precision 하락 노출.
        "name": "neg_edge_handled",
        "kind": "negative",
        "repo": "tests/fixtures/labelset/edge_fp_case",
        "files": ["src/pricing.py"],
        "expected": _exp(tv=[], perf=[]),
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# 실행
# ─────────────────────────────────────────────────────────────────────────────

def _new_file_diff(repo: Path, rel_files: list[str]) -> str:
    """src 파일을 '신규 파일 추가' 통합 diff 로 변환 → 전 줄이 changed 로 잡힘."""
    blocks: list[str] = []
    for rel in rel_files:
        text = (repo / rel).read_text(encoding="utf-8")
        lines = text.splitlines()
        body = "".join(f"+{ln}\n" for ln in lines)
        blocks.append(
            f"diff --git a/{rel} b/{rel}\n"
            "new file mode 100644\nindex 0000000..1111111\n"
            f"--- /dev/null\n+++ b/{rel}\n"
            f"@@ -0,0 +1,{len(lines)} @@\n{body}"
        )
    return "\n".join(blocks)


def _run_case(case: dict) -> list:
    repo = _ROOT / case["repo"]
    if case.get("diff_file"):
        diff = (_ROOT / case["diff_file"]).read_text(encoding="utf-8")
    else:
        diff = _new_file_diff(repo, case["files"])
    inp = Dev3Input(
        task_id=f"bench-{case['name']}",
        scan_id=0,
        pr_id=case["name"],
        pr_diff=diff,
        repo=RepoInfo(clone_url="https://github.com/example/repo", commit_sha="bench"),
        developer=Developer(id="bench_runner"),
    )
    return dev3_main.run(inp, str(repo))


_ALL_RULES = ["TEST-001", "TEST-003", "TEST-004", "PERF-001", "PERF-002", "PERF-003"]


def _format_report(result: dict, cases: list[dict]) -> str:
    import datetime

    lines: list[str] = []
    lines.append("# m3 탐지 정확도 벤치마크 — rule별 Precision/Recall/F1 (SESSION 8B)")
    lines.append("")
    lines.append(f"생성일: {datetime.date.today().isoformat()}")
    lines.append("환경: m3 컨테이너 내 직접 실행 / 무키(휴리스틱·결정적) / RAG off")
    lines.append("매칭: (rule_id, file) 멀티셋 (line·severity 는 식별자 아님)")
    lines.append("라벨: 사람이 rule 정의로 확정 (탐지기 출력 자동생성 아님 = 순환 금지)")
    lines.append("")
    lines.append(
        f"**표본 {result['n_cases']}건** "
        f"(양성 {result['n_positive']} + 음성 {result['n_negative']})"
    )
    for c in cases:
        lines.append(f"- `{c['name']}` ({c['kind']})")
    lines.append("")

    # rule별 표
    lines.append("## rule별 Precision / Recall / F1")
    lines.append("")
    lines.append("| rule | TP | FP | FN | Precision | Recall | F1 |")
    lines.append("|------|----|----|----|-----------|--------|----|")
    per_rule = result["per_rule"]
    for rule in _ALL_RULES:
        r = per_rule.get(rule)
        if r is None:
            lines.append(f"| {rule} | - | - | - | (미출현) | (미출현) | - |")
            continue
        lines.append(
            f"| {rule} | {r['tp']} | {r['fp']} | {r['fn']} | "
            f"{r['precision']:.3f} | {r['recall']:.3f} | {r['f1']:.3f} |"
        )
    o = result["overall"]
    lines.append(
        f"| **전체** | {o['tp']} | {o['fp']} | {o['fn']} | "
        f"**{o['precision']:.3f}** | **{o['recall']:.3f}** | **{o['f1']:.3f}** |"
    )
    lines.append("")
    lines.append(f"**합격 여부: {'PASS' if result['pass'] else 'FAIL'}** "
                 f"(전체 F1 ≥ 0.70 AND rule별 F1 ≥ 0.50)")
    lines.append("")

    # FP / FN
    lines.append("## 오탐(FP) — 헛다리")
    lines.append("")
    if result["fp_list"]:
        for fp in result["fp_list"]:
            lines.append(f"- `{fp['case']}` / {fp['rule_id']} / {fp['file']}")
    else:
        lines.append("- 없음")
    lines.append("")
    lines.append("## 미탐(FN) — 놓침")
    lines.append("")
    if result["fn_list"]:
        for fn in result["fn_list"]:
            lines.append(f"- `{fn['case']}` / {fn['rule_id']} / {fn['file']}")
    else:
        lines.append("- 없음")
    lines.append("")

    # 한계
    lines.append("## 한계")
    lines.append("")
    lines.append("- 표본 5건(양성 3·음성 2) — 통계적 유의성 낮음, 추세·약점 식별용.")
    lines.append("- TEST-003·PERF-003 은 무키 휴리스틱 모드 기준. LLM 모드는 결과가 달라질 수 있음(비결정).")
    lines.append("- 커버리지 의존 규칙(TEST-001/004)은 사전 생성 coverage.json 기반(실 Docker sandbox 미실행).")
    return "\n".join(lines)


def main() -> None:
    scored_cases = []
    for case in CASES:
        outputs = _run_case(case)
        scored_cases.append(
            {"name": case["name"], "outputs": outputs, "expected": case["expected"]}
        )

    result = evaluate_prf(scored_cases)
    report = _format_report(result, CASES)

    out_path = Path(__file__).parent / "benchmark_report.md"
    out_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"\n[benchmark] 저장: {out_path}")


if __name__ == "__main__":
    main()
