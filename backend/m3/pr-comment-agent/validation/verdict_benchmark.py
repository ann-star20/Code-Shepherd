"""SESSION 8C — verdict 정확도 벤치마크.

목적: 사람이 부여한 expected_verdict 와 실제 aggregate() 가 산출한 verdict 의 일치율 측정.

1커맨드 재실행 (m3 컨테이너 안 — LLM 불필요·결정적):
    cd /app/service/pr-comment-agent && uv run python validation/verdict_benchmark.py

산출:
    validation/verdict_report.md   (발표자료 §3 코멘트 품질평가 — verdict 칸)

원칙(정직, 8B 와 동일):
  - issue-set 은 8B 라벨셋(test-performance-agent/validation/benchmark.py CASES, 사람이 rule
    정의로 확정한 양성/음성 라벨)을 재사용해 재구성한다. 라벨은 (rule_id, file) — 거기에
    탐지기 정의가 부여하는 severity 를 매핑한다(아래 _SEVERITY 표, 출처 주석 명시).
  - expected_verdict 는 사람이 시나리오를 독립적으로 보고 부여(임계값 공식을 역적용하지 않음 = 순환 금지).
  - computed verdict 는 실제 aggregator.aggregate() 가 산출(코드가 결정, 하드코딩 아님).
  - 탐지 정확도(P/R/F1)는 8B 가 별도 측정 — 여기서는 "verdict 로직(임계값) 자체"의 정합성만 본다.

핵심 한계(정직): m3 6탐지기는 Critical 을 만들지 않는다(전부 Major/Minor). 따라서 escalate
(≥1 Critical)는 m3 단독으로는 절대 발생하지 않고, 실제로는 M2(정적/보안)의 Critical 로만 도달한다.
→ escalate 케이스(ext_*)는 그 교차모듈 상황을 모사한 것임을 명시한다.
"""
from __future__ import annotations

import datetime
import sys
from pathlib import Path

# pr-comment-agent 루트를 sys.path 에 (직접 실행 시) — eval.py 와 동일 패턴
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from aggregator import aggregate  # noqa: E402
from contracts import AgentOutput, Issue  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# rule → severity (탐지기 정의 출처 명시 — 재현·검증 가능)
#   TEST-001 coverage.py:55         Major
#   TEST-003 edge_cases.py:137/155  Minor
#   TEST-004 missing_funcs.py:63    Minor
#   PERF-001 complexity.py:73/90    Major(depth≥3) / Minor(depth==2)  ← 케이스별 명시
#   PERF-002 nplus1.py:49           Major
#   PERF-003 memory_leak.py:171/184 Minor
# ─────────────────────────────────────────────────────────────────────────────
_SEVERITY: dict[str, str] = {
    "TEST-001": "Major",
    "TEST-003": "Minor",
    "TEST-004": "Minor",
    "PERF-002": "Major",
    "PERF-003": "Minor",
    # PERF-001 은 depth 의존 → 케이스에서 severity 를 직접 지정한다.
}


# ─────────────────────────────────────────────────────────────────────────────
# 라벨셋 — 8B 재사용(5) + 확장(5). issues = [(severity, rule_id, file), ...]
#   expected_verdict 는 사람(리뷰어)이 시나리오를 보고 독립 부여.
# ─────────────────────────────────────────────────────────────────────────────

def _m(rule: str, file: str, n: int = 1) -> list[tuple[str, str, str]]:
    """rule→severity 표로 (severity, rule, file) n개 생성 (PERF-001 제외)."""
    return [(_SEVERITY[rule], rule, file)] * n


CASES: list[dict] = [
    # ── 8B 양성 3 ─────────────────────────────────────────────────────────────
    {
        "name": "pos_coverage_sample",
        "source": "8B",
        # 8B: TEST-001 + TEST-004×2 + TEST-003×3 + PERF-002 + PERF-001(find_dups 2중→Minor)
        "issues": (
            _m("TEST-001", "(전체)")
            + _m("TEST-004", "src/posts.py", 2)
            + _m("TEST-003", "src/posts.py", 3)
            + _m("PERF-002", "src/posts.py")
            + [("Minor", "PERF-001", "src/posts.py")]  # 2중 중첩 → Minor
        ),
        "expected_verdict": "rework",
        "rationale": "커버리지 20% + 미테스트 함수 + N+1 + O(n²) → 머지 전 수정 요청이 타당.",
    },
    {
        "name": "pos_perf_nplus1_complexity",
        "source": "8B",
        # 8B: TEST-003×2 + PERF-002 + PERF-001(find_triples 3중→Major)
        "issues": (
            _m("TEST-003", "src/app.py", 2)
            + _m("PERF-002", "src/app.py")
            + [("Major", "PERF-001", "src/app.py")]  # 3중 중첩 → Major
        ),
        "expected_verdict": "rework",
        "rationale": "N+1 쿼리 + O(n³) 3중 중첩루프 → 실제 성능 결함, 머지 전 수정 요청이 타당.",
    },
    {
        "name": "pos_memleak",
        "source": "8B",
        "issues": _m("PERF-003", "src/cache.py", 2),
        "expected_verdict": "lgtm",
        "rationale": "메모리 누수 의심 2건이나 탐지기 정의상 Minor(권고) → 참고 후 머지 가능.",
    },
    # ── 8B 음성 2 ─────────────────────────────────────────────────────────────
    {
        "name": "neg_clean",
        "source": "8B",
        "issues": [],
        "expected_verdict": "lgtm",
        "rationale": "진짜 깨끗한 코드 — 이슈 0건.",
    },
    {
        "name": "neg_edge_handled",
        "source": "8B",
        "issues": [],
        "expected_verdict": "lgtm",
        "rationale": "엣지케이스 이미 처리(정답 0건). 휴리스틱 FP 는 8B 의 precision 측정 대상이지 verdict 대상 아님.",
    },
    # ── 확장 5 (escalate + 임계값 경계, 교차모듈 상황 모사) ─────────────────────
    {
        "name": "ext_sqli_critical",
        "source": "extended (M2 모사)",
        "issues": [("Critical", "SEC-SQLI", "db/users.py")],
        "expected_verdict": "escalate",
        "rationale": "SQL 인젝션(Critical) — 시니어 검토 필요. m3 단독 불가, M2 정적/보안 출력으로만 도달.",
    },
    {
        "name": "ext_critical_plus_majors",
        "source": "extended (M2 모사)",
        "issues": [("Critical", "SEC-SECRET", "config.py")] + _m("PERF-002", "svc.py", 3),
        "expected_verdict": "escalate",
        "rationale": "하드코딩 시크릿(Critical)이 있으면 Major 수와 무관하게 escalate.",
    },
    {
        "name": "ext_three_nplus1",
        "source": "extended",
        "issues": _m("PERF-002", "svc.py", 3),
        "expected_verdict": "rework",
        "rationale": "N+1 3건(Major 3) — 임계값 도달, 수정 요청.",
    },
    {
        "name": "ext_minor_only",
        "source": "extended",
        "issues": [("Minor", "TEST-003", "a.py"), ("Minor", "PERF-003", "b.py")],
        "expected_verdict": "lgtm",
        "rationale": "권고성 Minor 만 — 머지 가능.",
    },
    {
        "name": "ext_many_minor",
        "source": "extended",
        "issues": _m("TEST-004", "a.py", 5),
        "expected_verdict": "lgtm",
        "rationale": "Minor 5건이어도 Major/Critical 0 → 머지 가능(Minor 는 verdict 를 올리지 않음).",
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# 로직
# ─────────────────────────────────────────────────────────────────────────────

def build_outputs(
    issues: list[tuple[str, str, str]], pr_id: str = "verdict-bench"
) -> list[AgentOutput]:
    """(severity, rule_id, file) 목록 → 단일 AgentOutput.

    같은 (rule_id, file) 라벨이 여러 개면 aggregate 의 dedup((rule_id,file,line))에 걸려
    사라지지 않도록 occurrence 마다 서로 다른 line 을 부여한다(라벨은 '서로 다른 실제 이슈'를 뜻함).
    """
    built: list[Issue] = []
    for idx, (severity, rule_id, file) in enumerate(issues, start=1):
        built.append(
            Issue(
                severity=severity,  # type: ignore[arg-type]
                file=file,
                line=idx,
                message=f"{rule_id} 라벨 이슈",
                rule_id=rule_id,
                suggestion="",
            )
        )
    return [AgentOutput(
        task_id="verdict-bench", scan_id=0, pr_id=pr_id,
        agent="combined", issues=built,
    )]


def compute_verdict(case: dict) -> str:
    """케이스 issue-set 을 실제 aggregate() 에 통과시켜 verdict 산출(코드가 결정)."""
    outputs = build_outputs(case["issues"], pr_id=case.get("name", "verdict-bench"))
    _, verdict, _ = aggregate(outputs)
    return verdict


def score_cases(cases: list[dict]) -> dict:
    """expected_verdict vs computed verdict 일치율·불일치 목록 집계."""
    per_case: list[dict] = []
    for c in cases:
        computed = compute_verdict(c)
        expected = c["expected_verdict"]
        per_case.append({
            "name": c["name"],
            "source": c.get("source", ""),
            "expected": expected,
            "computed": computed,
            "ok": computed == expected,
            "rationale": c.get("rationale", ""),
        })
    match = sum(1 for r in per_case if r["ok"])
    n = len(per_case)
    return {
        "n": n,
        "match": match,
        "match_rate": (match / n) if n else 0.0,
        "per_case": per_case,
        "mismatches": [r for r in per_case if not r["ok"]],
    }


# ─────────────────────────────────────────────────────────────────────────────
# 리포트
# ─────────────────────────────────────────────────────────────────────────────

_VERDICT_KO = {"lgtm": "통과", "rework": "수정요청", "escalate": "시니어검토"}


def format_report(result: dict) -> str:
    lines: list[str] = []
    lines.append("# m3 verdict 정확도 벤치마크 (SESSION 8C)")
    lines.append("")
    lines.append(f"생성일: {datetime.date.today().isoformat()}")
    lines.append("대상: aggregator.aggregate() 의 verdict 임계값(escalate≥1 Critical · rework≥3 Major)")
    lines.append("라벨: 8B 라벨셋(5) 재사용 + 확장(5). expected_verdict 는 사람이 독립 부여(순환 금지).")
    lines.append("severity: 탐지기 정의 매핑(TEST-001=Major, TEST-003/004=Minor, "
                 "PERF-001=depth별, PERF-002=Major, PERF-003=Minor).")
    lines.append("LLM 불필요 — 결정적·재현 가능.")
    lines.append("")
    lines.append(f"**verdict 일치율: {result['match']}/{result['n']} = "
                 f"{result['match_rate']*100:.0f}%**")
    lines.append("")
    lines.append("| 케이스 | 출처 | 기대(사람) | 산출(aggregate) | 일치 | 근거 |")
    lines.append("|---|---|---|---|:--:|---|")
    for r in result["per_case"]:
        mark = "✅" if r["ok"] else "❌"
        exp = f"{_VERDICT_KO[r['expected']]}({r['expected']})"
        com = f"{_VERDICT_KO[r['computed']]}({r['computed']})"
        lines.append(f"| `{r['name']}` | {r['source']} | {exp} | {com} | {mark} | {r['rationale']} |")
    lines.append("")
    if result["mismatches"]:
        lines.append("## 불일치 분석")
        lines.append("")
        for m in result["mismatches"]:
            lines.append(f"- `{m['name']}`: 기대 **{m['expected']}** vs 산출 **{m['computed']}** — {m['rationale']}")
        lines.append("")
        lines.append("> 공통 원인: m3 탐지기는 Critical 을 만들지 않아(전부 Major/Minor), N+1·O(n³) 같은 "
                     "실제 성능 결함도 Major 로 분류된다. 그런데 rework 임계값이 **Major 3건**이라, 현실적 PR "
                     "(Major 1~2건)이 lgtm 으로 통과한다. → MAJOR_REWORK_THRESHOLD 하향 또는 "
                     "PERF-002/PERF-001(deep) 의 escalate 승격 검토 권고.")
        lines.append("")
    lines.append("## 한계")
    lines.append("")
    lines.append("- 표본 10건(8B 5 + 확장 5) — 추세·임계값 점검용(통계적 유의성 아님).")
    lines.append("- escalate 는 m3 단독 불가(Critical 미생성) → ext_* 는 M2 교차모듈 상황 모사.")
    lines.append("- expected_verdict 는 사람 판단 — pos_memleak(Minor 누수) 등 일부는 리뷰어에 따라 이견 가능.")
    return "\n".join(lines)


def main() -> None:
    result = score_cases(CASES)
    report = format_report(result)
    out = Path(__file__).parent / "verdict_report.md"
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"\n[verdict-bench] 저장: {out}")


if __name__ == "__main__":
    main()
