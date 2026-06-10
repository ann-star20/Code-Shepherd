"""bench/collector.py — 단계별 타이밍 집계·통계·리포트 생성.

Public API:
  percentile(values, pct)      → float
  build_stats(timings)         → {stage: {p50, p95, min, max, n}}
  format_report_table(...)     → markdown string
  split_cold_warm(runs)        → (cold_dict, warm_list)

측정 못 한 단계는 결과 dict에서 완전히 생략(가짜 0 금지).
"""
from __future__ import annotations

import math
from typing import Any


# ──────────────────────────────────────────────
# percentile
# ──────────────────────────────────────────────

def percentile(values: list[float], pct: float) -> float:
    """정렬된 값 목록에서 pct 백분위수를 반환한다 (linear interpolation).

    Args:
        values: 숫자 리스트 (정렬 여부 무관 — 내부에서 정렬함)
        pct   : 0~100 범위 백분위 (예: 50, 95)

    Returns:
        float — 해당 백분위값
    """
    if not values:
        raise ValueError("values가 비어 있습니다")
    sorted_v = sorted(values)
    n = len(sorted_v)
    if n == 1:
        return float(sorted_v[0])
    # numpy-compatible linear interpolation
    idx = (pct / 100) * (n - 1)
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return float(sorted_v[lo])
    frac = idx - lo
    return float(sorted_v[lo] * (1 - frac) + sorted_v[hi] * frac)


# ──────────────────────────────────────────────
# build_stats
# ──────────────────────────────────────────────

def build_stats(
    timings: dict[str, list[float]]
) -> dict[str, dict[str, Any]]:
    """단계별 ms 리스트 → p50·p95·min·max·n 집계 딕셔너리.

    입력에 없는 단계는 결과에도 없음 (가짜 0 금지).
    """
    result: dict[str, dict[str, Any]] = {}
    for stage, ms_list in timings.items():
        if not ms_list:
            continue
        result[stage] = {
            "p50": round(percentile(ms_list, 50), 1),
            "p95": round(percentile(ms_list, 95), 1),
            "min": round(min(ms_list), 1),
            "max": round(max(ms_list), 1),
            "n":   len(ms_list),
        }
    return result


# ──────────────────────────────────────────────
# format_report_table
# ──────────────────────────────────────────────

_STAGE_ORDER = [
    "parse_diff",
    "prepare_repo",
    "coverage",
    "sandbox",
    "missing_funcs",
    "nplus1",
    "complexity",
    "code_context_llm",
    "framework",
    "rag",
    "dev3.run",
]

_STAGE_LABEL = {
    "parse_diff":       "parse_diff",
    "prepare_repo":     "clone (prepare_repo)",
    "coverage":         "coverage (sandbox/pytest)",
    "sandbox":          "sandbox (Docker pytest)",
    "missing_funcs":    "missing_funcs",
    "nplus1":           "nplus1",
    "complexity":       "complexity",
    "code_context_llm": "enrich (code_context LLM)",
    "framework":        "framework",
    "rag":              "rag",
    "dev3.run":         "end_to_end",
}


def format_report_table(
    stats: dict[str, dict[str, Any]],
    n: int,
    prs: list[str],
    *,
    rag_enabled: bool = False,
    cold_stats: dict[str, dict[str, Any]] | None = None,
    warm_stats: dict[str, dict[str, Any]] | None = None,
    env_note: str = "",
) -> str:
    """단계별 통계를 발표 가능한 markdown 표로 반환한다.

    Args:
        stats       : build_stats() 결과 (warm 또는 combined)
        n           : 총 측정 횟수
        prs         : PR 식별자 목록
        rag_enabled : RAG 켜졌으면 True (꺼지면 rag 행에 '(off)')
        cold_stats  : 첫 번째 실행 통계 (있으면 cold/warm 구분 표 추가)
        warm_stats  : 2번째 이후 실행 통계
        env_note    : 환경 설명 (예: "m3 컨테이너 내 직접 실행")
    """
    lines: list[str] = []

    # 메타정보
    lines.append(f"**N={n}**, PR: {', '.join(prs)}")
    if env_note:
        lines.append(f"환경: {env_note}")
    lines.append("")

    # 단계별 통계 표 (warm 또는 combined)
    table_label = "warm 실행" if cold_stats else "전체"
    lines.append(f"### 단계별 소요 시간 ({table_label})")
    lines.append("")
    lines.append("| 단계 | p50 (ms) | p95 (ms) | min | max | N |")
    lines.append("|------|----------|----------|-----|-----|---|")

    used_stats = warm_stats if warm_stats is not None else stats

    for stage in _STAGE_ORDER:
        label = _STAGE_LABEL.get(stage, stage)
        if stage == "rag" and not rag_enabled and stage not in used_stats:
            lines.append(f"| {label} | (off) | (off) | - | - | - |")
            continue
        if stage not in used_stats:
            continue
        s = used_stats[stage]
        lines.append(
            f"| {label} | {s['p50']} | {s['p95']} | {s['min']} | {s['max']} | {s['n']} |"
        )

    # 기타 측정된 단계 (STAGE_ORDER에 없는 것)
    for stage, s in used_stats.items():
        if stage not in _STAGE_ORDER:
            lines.append(
                f"| {stage} | {s['p50']} | {s['p95']} | {s['min']} | {s['max']} | {s['n']} |"
            )

    # cold vs warm 구분 표
    if cold_stats is not None:
        lines.append("")
        lines.append("### cold vs warm 비교")
        lines.append("")
        lines.append("| 단계 | cold p50 | warm p50 | 차이 |")
        lines.append("|------|----------|----------|------|")
        all_stages = sorted(set(list(cold_stats.keys()) + list((warm_stats or {}).keys())))
        for stage in all_stages:
            label = _STAGE_LABEL.get(stage, stage)
            c_p50 = cold_stats.get(stage, {}).get("p50", "-")
            w_p50 = (warm_stats or {}).get(stage, {}).get("p50", "-")
            if isinstance(c_p50, float) and isinstance(w_p50, float):
                diff = f"+{c_p50 - w_p50:.1f}" if c_p50 > w_p50 else f"{c_p50 - w_p50:.1f}"
            else:
                diff = "-"
            lines.append(f"| {label} | {c_p50} | {w_p50} | {diff} |")

    # 병목 식별
    if used_stats:
        ranked = sorted(used_stats.items(), key=lambda kv: kv[1]["p50"], reverse=True)
        top2 = [_STAGE_LABEL.get(k, k) for k, _ in ranked[:2]]
        lines.append("")
        lines.append(f"**병목**: {', '.join(top2)}")

    return "\n".join(lines)


# ──────────────────────────────────────────────
# split_cold_warm
# ──────────────────────────────────────────────

def split_cold_warm(
    runs: list[dict[str, list[float]]]
) -> tuple[dict[str, list[float]], list[dict[str, list[float]]]]:
    """실행 목록에서 첫 실행(cold)과 나머지(warm)를 분리한다.

    Args:
        runs: 각 실행의 {stage: [ms]} 딕셔너리 리스트

    Returns:
        (cold_timings, warm_timings_list)
    """
    if not runs:
        return {}, []
    return runs[0], runs[1:]
