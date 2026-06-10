"""SESSION 8C — '왜 한 줄' 코멘트 품질 LLM-as-judge 채점기.

refine() 가 생성한 '왜(한 줄)'을 루브릭 4축(1~5)으로 채점한다.
judge 모델 호출(_call_judge)은 seam 으로 분리 → mock 가능, 모델 교체 가능(JUDGE_MODEL).

루브릭(재현·검증 가능하게 코드/리포트에 명시):
  - consistency      : 판정(verdict)과의 정합성
  - actionable       : 도움됨(무엇을/왜 고칠지 실천적 단서)
  - tone             : 대상 skill_level(junior/mid/senior)에 적합한 톤
  - no_hallucination : 이슈 목록에 없는 사실을 지어내지 않음

정직 원칙:
  - LLM 미가용(키 없음·429·빈 응답·형식오류) → 해당 케이스 **skip**(가짜 점수 금지).
  - 전 케이스 skip → status="skip" + 사유.
  - judge 모델·케이스 수·루브릭을 리포트에 명시.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# pr-comment-agent 루트를 sys.path 에 (직접 실행 시)
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# 채점관 기본 모델 — 쿼터 안전한 flash-lite. JUDGE_MODEL 로 교체 가능(모델 추상화).
DEFAULT_JUDGE_MODEL = "gemini-2.5-flash-lite"

# 낮은 점수 플래그 임계값(축 ≤ 2 면 '낮은 점수 사례'로 노출)
LOW_THRESHOLD = 2

_AXES = ("consistency", "actionable", "tone", "no_hallucination")

JUDGE_RUBRIC: dict[str, str] = {
    "consistency": "판정(verdict)과의 정합성 — 한 줄이 판정과 모순되지 않는가",
    "actionable": "도움됨 — 무엇을/왜 고쳐야 하는지 실천적 단서를 주는가",
    "tone": "톤 — 대상 개발자 수준(junior/mid/senior)에 적합한가",
    "no_hallucination": "환각 없음 — 이슈 목록에 없는 사실을 지어내지 않는가",
}


# ── 프롬프트 ──────────────────────────────────────────────────────────────────

def build_judge_prompt(
    why: str, verdict: str, skill_level: str, issues_summary: str
) -> str:
    """채점 프롬프트 — 루브릭 4축을 명시하고 엄격 JSON 점수를 요구."""
    rubric_lines = "\n".join(f"- {k} (1~5): {v}" for k, v in JUDGE_RUBRIC.items())
    return (
        "당신은 코드리뷰 코멘트 품질 채점관입니다. 아래 '한 줄 리뷰 코멘트'를 루브릭으로 채점하세요.\n\n"
        f"[판정(verdict)] {verdict}\n"
        f"[대상 개발자 수준(skill_level)] {skill_level}\n"
        f"[탐지된 이슈 요약]\n{issues_summary}\n\n"
        f"[채점할 한 줄]\n{why}\n\n"
        "[루브릭 — 각 축 1~5점]\n"
        f"{rubric_lines}\n\n"
        "오직 아래 JSON 객체 하나만 출력하세요(코드펜스·설명 금지):\n"
        '{"consistency": <1-5>, "actionable": <1-5>, "tone": <1-5>, '
        '"no_hallucination": <1-5>, "reason": "<짧은 근거 한 줄>"}'
    )


# ── seam: 실제 judge LLM 호출 (mock 대상, 모델 교체 가능) ──────────────────────

def _call_judge(prompt: str) -> str:
    """채점관 LLM 호출(Gemini). JUDGE_MODEL→LLM_MODEL→flash-lite 순. 키 없으면 ''."""
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return ""
    from google import genai  # type: ignore  # noqa: PLC0415

    client = genai.Client(api_key=api_key)
    model = os.getenv("JUDGE_MODEL") or os.getenv("LLM_MODEL") or DEFAULT_JUDGE_MODEL
    response = client.models.generate_content(model=model, contents=prompt)
    return response.text


def judge_model_name() -> str:
    """현재 채점에 쓰일 judge 모델명(리포트 명시용)."""
    return os.getenv("JUDGE_MODEL") or os.getenv("LLM_MODEL") or DEFAULT_JUDGE_MODEL


def _pace() -> None:
    """무료쿼터 RPM 회피용 호출 간 간격(JUDGE_PACE_SEC초, 기본 0 → 테스트는 즉시)."""
    try:
        sec = float(os.getenv("JUDGE_PACE_SEC", "0") or 0)
    except ValueError:
        sec = 0.0
    if sec > 0:
        time.sleep(sec)


# ── 파싱: judge 응답 → 점수 dict / skip(None) ─────────────────────────────────

def parse_judge(raw: str) -> dict | None:
    """judge 응답 텍스트 → {4축 int(1~5) + reason} 또는 None(skip).

    코드펜스/후행 prose 에 견고. 축 누락·비숫자·빈 응답·JSON 아님 → None.
    """
    if not raw or not raw.strip():
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().lstrip().startswith("json"):
            text = text.lstrip()[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    out: dict = {}
    for axis in _AXES:
        if axis not in data:
            return None
        try:
            v = int(round(float(data[axis])))
        except (TypeError, ValueError):
            return None
        out[axis] = max(1, min(5, v))
    out["reason"] = str(data.get("reason", "")).strip()
    return out


# ── 케이스 1건 채점 ────────────────────────────────────────────────────────────

def judge_one(case: dict) -> dict | None:
    """case['why'] 한 줄을 채점. 미응답·예외·파싱불가 → None(skip)."""
    prompt = build_judge_prompt(
        why=case["why"],
        verdict=case["verdict"],
        skill_level=case["skill_level"],
        issues_summary=case["issues_summary"],
    )
    try:
        raw = _call_judge(prompt)
    except Exception:
        return None
    return parse_judge(raw)


# ── 집계 ──────────────────────────────────────────────────────────────────────

def score_comments(cases: list[dict]) -> dict:
    """전 케이스 채점 → 항목별 평균·전체 평균·낮은점수·skip 집계(정직)."""
    scored: list[dict] = []
    skipped: list[dict] = []
    for idx, c in enumerate(cases):
        if idx:
            _pace()  # 호출 간 간격 (첫 호출 제외)
        s = judge_one(c)
        if s is None:
            skipped.append({
                "name": c["name"],
                "reason": "judge 미응답/파싱불가 (LLM 미가용·쿼터(429)·형식오류)",
            })
        else:
            scored.append({
                "name": c["name"],
                "skill_level": c.get("skill_level", ""),
                "why": c.get("why", ""),
                "why_source": c.get("why_source", ""),
                **s,
            })

    n = len(scored)
    if n == 0:
        return {
            "scored": 0, "skipped": len(skipped), "status": "skip",
            "skip_reason": "전 케이스 judge 미가용 — 가짜 점수 금지(정직 skip).",
            "judge_model": judge_model_name(),
            "per_axis": {a: None for a in _AXES}, "overall": None,
            "low_scores": [], "skipped_list": skipped, "scored_list": [],
        }

    per_axis = {a: round(sum(r[a] for r in scored) / n, 3) for a in _AXES}
    overall = round(sum(per_axis.values()) / len(_AXES), 3)
    low = [r for r in scored if any(r[a] <= LOW_THRESHOLD for a in _AXES)]
    return {
        "scored": n, "skipped": len(skipped), "status": "ok",
        "judge_model": judge_model_name(),
        "per_axis": per_axis, "overall": overall,
        "low_scores": low, "skipped_list": skipped, "scored_list": scored,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 실 평가 하니스 — verdict 라벨셋 재사용해 '왜 한 줄' 생성 후 채점 (≥10건)
#   생성도 LLM(refine 경로) → 쿼터 소진 시 휴리스틱(정직 표기) + judge skip 가능.
# ─────────────────────────────────────────────────────────────────────────────

def _issues_summary(issue_tuples: list[tuple[str, str, str]]) -> str:
    return "\n".join(f"- [{sev}] {rule} ({file})" for sev, rule, file in issue_tuples) or "(없음)"


# 채점 케이스 plan — (verdict_benchmark 케이스명, skill_level).
# 앞 5건이 verdict 3종(lgtm/rework/escalate) + skill 3종을 모두 덮도록 정렬
# → 적은-케이스 모드(max_cases=5, 무료쿼터용 ~10호출)에서도 발표 대표성 유지.
_JUDGE_PLAN: list[tuple[str, str]] = [
    ("ext_sqli_critical", "senior"),            # escalate, senior
    ("ext_three_nplus1", "mid"),                # rework, mid
    ("pos_perf_nplus1_complexity", "junior"),   # lgtm, junior (실제 N+1+O(n³))
    ("pos_coverage_sample", "mid"),             # lgtm, mid
    ("ext_critical_plus_majors", "junior"),     # escalate, junior
    ("pos_memleak", "senior"),                  # lgtm, senior
    ("ext_minor_only", "mid"),                  # lgtm, mid
    ("ext_many_minor", "junior"),               # lgtm, junior
    ("pos_perf_nplus1_complexity", "senior"),   # skill 변형
    ("ext_sqli_critical", "mid"),               # skill 변형
]


def make_judge_cases(max_cases: int | None = None) -> list[dict]:
    """verdict 라벨셋의 이슈 케이스로 '왜 한 줄'을 생성 → 채점 케이스 목록.

    max_cases: 앞에서부터 N건만(무료쿼터용 적은-케이스 모드). None=전체(10).
    skill_level 을 섞어 톤 축 검증. why 는 refine 의 LLM 경로(_llm_why)로 생성,
    실패(쿼터·키없음) 시 휴리스틱(_heuristic_why) + source 표기.
    """
    import llm_refiner
    from contracts import CombinedIssue
    try:  # 패키지 import(pytest) vs 스크립트 직접 실행 둘 다 지원
        from validation.verdict_benchmark import CASES as V_CASES, compute_verdict
    except ModuleNotFoundError:
        from verdict_benchmark import CASES as V_CASES, compute_verdict

    by_name = {c["name"]: c for c in V_CASES}
    plan = _JUDGE_PLAN if max_cases is None else _JUDGE_PLAN[:max_cases]

    cases: list[dict] = []
    for idx, (name, skill) in enumerate(plan):
        c = by_name[name]
        verdict = compute_verdict(c)
        issues = [
            CombinedIssue(severity=sev, file=file, line=i + 1,  # type: ignore[arg-type]
                          message=f"{rule} 이슈", rule_id=rule, suggestion="")
            for i, (sev, rule, file) in enumerate(c["issues"])
        ]
        why = ""
        if llm_refiner._has_api_key():
            if idx:
                _pace()  # 생성 호출 간 간격
            why = llm_refiner._llm_why(issues, verdict, skill)
        source = "llm"
        if not why:
            why = llm_refiner._heuristic_why(issues, verdict)
            source = "heuristic"
        cases.append({
            "name": f"{c['name']}@{skill}",
            "why": why, "why_source": source,
            "verdict": verdict, "skill_level": skill,
            "issues_summary": _issues_summary(c["issues"]),
        })
    return cases


def format_report(result: dict, cases: list[dict]) -> str:
    import datetime
    lines: list[str] = []
    lines.append("# m3 '왜 한 줄' 코멘트 품질 — LLM-as-judge (SESSION 8C)")
    lines.append("")
    lines.append(f"생성일: {datetime.date.today().isoformat()}")
    lines.append(f"judge 모델: `{result.get('judge_model')}`  (JUDGE_MODEL 로 교체 가능)")
    lines.append(f"케이스 수: {len(cases)}건 (verdict 라벨셋 이슈 케이스 + skill 변형)")
    n_llm = sum(1 for c in cases if c.get("why_source") == "llm")
    lines.append(f"피평가 '왜 한 줄' 생성: LLM {n_llm}건 / 휴리스틱 {len(cases)-n_llm}건")
    lines.append("")
    lines.append("## 루브릭 (각 축 1~5)")
    for k, v in JUDGE_RUBRIC.items():
        lines.append(f"- **{k}**: {v}")
    lines.append("")

    if result["status"] == "skip":
        lines.append(f"## 결과: ⏭️ SKIP — {result['skip_reason']}")
        lines.append("")
        lines.append("> 정직 원칙상 가짜 점수를 만들지 않는다. 쿼터 회복(매일 자정 PT≈한국 17시 리셋) 후 재실행:")
        lines.append("> ```")
        lines.append("> # 무료티어 권장: 5케이스(~10호출) — 하루 한도(20) 안에 들어옴")
        lines.append("> docker compose exec m3 sh -lc 'cd /app/service/pr-comment-agent && \\")
        lines.append(">   LLM_MODEL=gemini-2.5-flash-lite JUDGE_MAX_CASES=5 uv run python validation/comment_judge.py'")
        lines.append("> ```")
        if result["skipped_list"]:
            lines.append("")
            lines.append(f"skip 케이스 {len(result['skipped_list'])}건 (사유 동일: judge 미가용/쿼터).")
        return "\n".join(lines)

    lines.append(f"**채점 {result['scored']}건 / skip {result['skipped']}건 · "
                 f"전체 평균 {result['overall']}/5**")
    lines.append("")
    pa = result["per_axis"]
    lines.append("| 축 | 평균 |")
    lines.append("|---|:--:|")
    for a in _AXES:
        lines.append(f"| {a} | {pa[a]} |")
    lines.append(f"| **전체** | **{result['overall']}** |")
    lines.append("")
    lines.append("## 케이스별 점수")
    lines.append("| 케이스 | skill | 생성 | C | A | T | H | reason |")
    lines.append("|---|---|---|:--:|:--:|:--:|:--:|---|")
    for r in result["scored_list"]:
        lines.append(f"| `{r['name']}` | {r['skill_level']} | {r['why_source']} | "
                     f"{r['consistency']} | {r['actionable']} | {r['tone']} | "
                     f"{r['no_hallucination']} | {r['reason']} |")
    lines.append("")
    if result["low_scores"]:
        lines.append("## 낮은 점수 사례 (축 ≤ 2)")
        for r in result["low_scores"]:
            lines.append(f"- `{r['name']}` — \"{r['why']}\" / {r['reason']}")
        lines.append("")
    if result["skipped_list"]:
        lines.append(f"## skip {len(result['skipped_list'])}건")
        for s in result["skipped_list"]:
            lines.append(f"- `{s['name']}` — {s['reason']}")
    lines.append("")
    lines.append("## 한계")
    lines.append("- judge=피평가와 동일 계열(Gemini) 가능 — 동일모델 자기채점 편향 가능성 명시.")
    lines.append("- 표본 소수 + 무료쿼터 의존(429 시 비결정·skip).")
    return "\n".join(lines)


def main() -> None:
    mx = os.getenv("JUDGE_MAX_CASES", "").strip()
    max_cases = int(mx) if mx else None  # 적은-케이스 모드(무료쿼터): JUDGE_MAX_CASES=5
    cases = make_judge_cases(max_cases=max_cases)
    result = score_comments(cases)
    report = format_report(result, cases)
    out = Path(__file__).parent / "comment_judge_report.md"
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"\n[comment-judge] 저장: {out}")


if __name__ == "__main__":
    main()
