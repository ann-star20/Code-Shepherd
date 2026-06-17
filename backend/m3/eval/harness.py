"""평가 하네스 - 골든셋 자동 실행 + 지표 4종 + 환각 string-match 자동검증 (세션 B 소유)

브리프 §4 명세:
- `make eval`: 전체 실행 → 표 리포트 (탐지율 / 오탐 / 환각률 / 지침공백 정확도)
- `make eval-one PR=pr_003` / `make eval-failed`: 부분 실행 (브리프 §9.2)
- 환각 자동검증 (브리프 §4.2 - 이 코드가 그 검증):
  · Finding.rule_id 가 corpus/ 에 실존하는가
  · Finding.rule_quote 가 해당 규칙 문서에 string-match 되는가 (공백 정규화 허용, 퍼지 매칭 없음)
  · Finding.evidence_lines 각 줄이 diff 에 string-match 되는가
- 실행 기록 JSON: eval/runs/run_*.json + latest.json (--failed 가 latest 를 읽음, 부분 실행은 병합)
- temperature 0 은 src/config.py 가 고정. golden/·contracts/ 는 읽기 전용 (게이트 1·2).

파이프라인 호출은 계약 경계인 src.adapters.streamlit_adapter.review() 만 사용한다
(src 내부 구조 비의존). 미구현(D2 전)이면 케이스가 not_implemented 로 기록된다.
골든 케이스의 변경 파일 전문은 repo_meta["files"] = {상대경로: 내용} 로 전달한다.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
import traceback
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

import yaml

from contracts import SCHEMA_VERSION, Finding, GoldenLabel, ReviewOutput

REPO_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_DIR = REPO_ROOT / "golden"
RUNS_DIR = REPO_ROOT / "eval" / "runs"

CATEGORY_KR = {"violation": "위반", "normal": "정상", "gap": "지침공백"}


def _default_corpus_dir() -> Path:
    """src/config.py 의 CORPUS_DIR 단일 설정을 따른다 (임포트 불가 시 corpus/)."""
    try:
        from src import config
        p = Path(config.CORPUS_DIR)
    except Exception:
        p = Path("corpus")
    return p if p.is_absolute() else REPO_ROOT / p


# ── 코퍼스 인덱스 ────────────────────────────────────────────────────────

_RULE_HEADER = re.compile(r"^#\s+\[?(CONV-[A-Z0-9]+-\d+)\]?", re.MULTILINE)
_SECTION_HEADER = re.compile(r"^##\s+(§\S+)[^\n]*$", re.MULTILINE)


def _norm_ws(s: str) -> str:
    """공백 정규화 - 연속 공백·개행을 한 칸으로. 퍼지 매칭이 아니라 표기 차이 흡수용."""
    return " ".join(s.split())


@dataclass
class RuleDoc:
    """corpus/*.md 규칙 문서 1개 (rule_quote 검증의 원천)."""
    rule_id: str
    path: str                  # 출처 표기용 상대/절대 경로 문자열
    text: str                  # 문서 전문
    norm_text: str             # 공백 정규화본
    sections: dict[str, str]   # {"§1": 본문, ...} - ingestion 청크 단위와 동일


def build_corpus_index(corpus_dir: Path | str) -> dict[str, RuleDoc]:
    """corpus/*.md → {rule_id: RuleDoc}. rule_id 헤더(`# [CONV-XXX-NNN]`) 없는 파일은 제외."""
    corpus_dir = Path(corpus_dir)
    idx: dict[str, RuleDoc] = {}
    if not corpus_dir.is_dir():
        return idx
    for p in sorted(corpus_dir.rglob("*.md")):
        text = p.read_text(encoding="utf-8-sig")
        m = _RULE_HEADER.search(text)
        if not m:
            continue  # README 등 규칙 문서 아님
        rule_id = m.group(1)
        if rule_id in idx:
            print(f"[harness] 경고: {rule_id} 중복 선언 - {p} 무시 (첫 문서 우선)")
            continue
        matches = list(_SECTION_HEADER.finditer(text))
        sections = {
            sm.group(1): text[sm.end(): matches[i + 1].start() if i + 1 < len(matches) else len(text)].strip()
            for i, sm in enumerate(matches)
        }
        idx[rule_id] = RuleDoc(rule_id, str(p), text, _norm_ws(text), sections)
    return idx


# ── 환각 자동검증 (브리프 §4.2 필수) ────────────────────────────────────

def verify_finding(finding: Finding, diff: str, corpus_idx: dict[str, RuleDoc]) -> dict:
    """Finding 1건의 인용 검증. 전부 string-match - LLM·퍼지 매칭 없음.

    반환: {rule_id_ok, quote_ok, evidence_ok, ok, matched_section, reasons[]}
    """
    reasons: list[str] = []

    doc = corpus_idx.get(finding.rule_id)
    rule_id_ok = doc is not None
    if not rule_id_ok:
        reasons.append(f"rule_id 미실존: {finding.rule_id}")

    quote = finding.rule_quote.strip()
    quote_ok = False
    matched_section: str | None = None
    if not quote:
        reasons.append("rule_quote 비어 있음")
    elif doc is None:
        reasons.append("rule_quote 검증 불가 (rule_id 미실존)")
    else:
        nq = _norm_ws(quote)
        quote_ok = quote in doc.text or nq in doc.norm_text
        if quote_ok:
            for name, body in doc.sections.items():
                if quote in body or nq in _norm_ws(body):
                    matched_section = name
                    break
        else:
            reasons.append(f"rule_quote 불일치: {finding.rule_id} 문서에 해당 문구 없음")

    norm_diff = _norm_ws(diff)
    bad_lines = [
        line for line in finding.evidence_lines
        if line.strip() and not (line in diff or line.strip() in diff or _norm_ws(line) in norm_diff)
    ]
    evidence_ok = not bad_lines
    reasons.extend(f"evidence 불일치(diff에 없음): {line.strip()[:80]}" for line in bad_lines)

    return {
        "rule_id_ok": rule_id_ok,
        "quote_ok": quote_ok,
        "evidence_ok": evidence_ok,
        "ok": rule_id_ok and quote_ok and evidence_ok,
        "matched_section": matched_section,
        "reasons": reasons,
    }


# ── 골든셋 로더 (golden/ 은 읽기 전용 - 게이트 1) ───────────────────────

@dataclass
class GoldenCase:
    pr_id: str
    path: Path
    diff: str
    file_paths: list[str]      # diff 의 +++/--- 헤더에서 파싱
    files: dict[str, str]      # files/ 하위 변경 파일 전문 {상대경로: 내용}
    label: GoldenLabel
    category: str              # violation | normal | gap


def _parse_file_paths(diff: str) -> list[str]:
    """unified diff 에서 변경 파일 상대경로 추출 (삭제 파일은 --- a/ 경로 사용)."""
    paths: list[str] = []
    last_minus: str | None = None
    for raw in diff.splitlines():
        line = raw.rstrip()
        if line.startswith("--- "):
            t = line[4:].strip()
            last_minus = None if t == "/dev/null" else (t[2:] if t.startswith("a/") else t)
        elif line.startswith("+++ "):
            t = line[4:].strip()
            p = last_minus if t == "/dev/null" else (t[2:] if t.startswith("b/") else t)
            if p and p not in paths:
                paths.append(p)
    return paths


def load_golden_cases(golden_dir: Path | str = GOLDEN_DIR) -> list[GoldenCase]:
    golden_dir = Path(golden_dir)
    cases: list[GoldenCase] = []
    if not golden_dir.is_dir():
        return cases
    for d in sorted(golden_dir.iterdir()):
        if not d.is_dir() or not d.name.startswith("pr_"):
            continue
        diff_p, label_p = d / "diff.patch", d / "label.yaml"
        if not diff_p.is_file() or not label_p.is_file():
            raise FileNotFoundError(f"골든 케이스 불완전: {d.name} 에 diff.patch + label.yaml 필요")
        diff = diff_p.read_text(encoding="utf-8-sig")
        label = GoldenLabel(**yaml.safe_load(label_p.read_text(encoding="utf-8-sig")))
        files: dict[str, str] = {}
        files_dir = d / "files"
        if files_dir.is_dir():
            files = {
                f.relative_to(files_dir).as_posix(): f.read_text(encoding="utf-8-sig")
                for f in sorted(files_dir.rglob("*")) if f.is_file()
            }
        category = "gap" if label.expected == "gap" else ("violation" if label.expected else "normal")
        cases.append(GoldenCase(d.name, d, diff, _parse_file_paths(diff), files, label, category))
    return cases


# ── 케이스 실행·평가 ─────────────────────────────────────────────────────

ReviewFn = Callable[[GoldenCase], ReviewOutput]


def default_review_fn(case: GoldenCase) -> ReviewOutput:
    """실 파이프라인 호출 - 계약 경계(streamlit_adapter.review)만 사용."""
    from src.adapters.streamlit_adapter import review

    repo_meta = {"source": "golden", "pr_id": case.pr_id, "files": case.files}
    return review(case.diff, case.file_paths, repo_meta)


def evaluate_case(case: GoldenCase, output: ReviewOutput, corpus_idx: dict[str, RuleDoc]) -> dict:
    """라벨 대조 + 환각 검증 → 케이스 결과 dict (JSON 직렬화 가능)."""
    verifies = [
        {"rule_id": f.rule_id, "verdict": f.verdict, **verify_finding(f, case.diff, corpus_idx)}
        for f in output.findings
    ]
    halluc_bad = sum(1 for v in verifies if not v["ok"])
    n_violations = sum(1 for f in output.findings if f.verdict == "violation")
    predicted = list(dict.fromkeys(f.rule_id for f in output.findings if f.verdict == "violation"))
    gap_reported = output.gap_report is not None

    expected_ids = [e.rule_id for e in case.label.expected] if case.category == "violation" else []
    missing = [r for r in expected_ids if r not in predicted]
    extra = [r for r in predicted if r not in expected_ids]

    detected: bool | None = None
    fp_count = 0
    if case.category == "violation":
        detected = not missing
        label_ok = detected and not extra and not gap_reported
    elif case.category == "normal":
        fp_count = n_violations
        label_ok = fp_count == 0 and not gap_reported
    else:  # gap
        label_ok = gap_reported and n_violations == 0

    return {
        "pr_id": case.pr_id,
        "category": case.category,
        "status": "ok",
        "pass": label_ok and halluc_bad == 0,
        "expected": "gap" if case.category == "gap" else expected_ids,
        "predicted_violations": predicted,
        "missing": missing,
        "extra": extra,
        "detected": detected,
        "fp_count": fp_count,
        "gap_expected": case.category == "gap",
        "gap_reported": gap_reported,
        "halluc": {"bad": halluc_bad, "checked": len(verifies), "details": verifies},
        "error": None,
        "findings": [f.model_dump() for f in output.findings],
        "comment_md": output.comment_md,
        "gap_report": output.gap_report.model_dump() if output.gap_report else None,
    }


def _error_result(case: GoldenCase, status: str, message: str, tb: str | None = None) -> dict:
    expected_ids = [e.rule_id for e in case.label.expected] if case.category == "violation" else []
    return {
        "pr_id": case.pr_id,
        "category": case.category,
        "status": status,                # "error" | "not_implemented"
        "pass": False,
        "expected": "gap" if case.category == "gap" else expected_ids,
        "predicted_violations": [],
        "missing": expected_ids,
        "extra": [],
        "detected": False if case.category == "violation" else None,
        "fp_count": 0,
        "gap_expected": case.category == "gap",
        "gap_reported": False,
        "halluc": {"bad": 0, "checked": 0, "details": []},
        "error": message,
        "traceback": tb,
        "findings": [],
        "comment_md": None,
        "gap_report": None,
    }


def run_cases(cases: list[GoldenCase], corpus_idx: dict[str, RuleDoc],
              review_fn: ReviewFn = default_review_fn) -> list[dict]:
    results: list[dict] = []
    for case in cases:
        try:
            output = review_fn(case)
        except NotImplementedError as e:
            results.append(_error_result(case, "not_implemented", f"파이프라인 미구현(D2 통합 전): {e}"))
            continue
        except Exception as e:  # 실패 케이스도 기록하고 계속 - 원인 분류는 run JSON 으로
            results.append(_error_result(case, "error", f"{type(e).__name__}: {e}", traceback.format_exc()))
            continue
        results.append(evaluate_case(case, output, corpus_idx))
    return results


# ── 지표 4종 (브리프 §4.2) ──────────────────────────────────────────────

def compute_metrics(results: list[dict]) -> dict:
    viol = [r for r in results if r["category"] == "violation"]
    norm = [r for r in results if r["category"] == "normal"]
    gap = [r for r in results if r["category"] == "gap"]
    return {
        "detection": {"hit": sum(1 for r in viol if r["detected"]), "total": len(viol)},
        "false_positive": {
            "count": sum(r["fp_count"] for r in norm),
            "normal_prs": len(norm),
            "prs_with_fp": sum(1 for r in norm if r["fp_count"]),
        },
        "hallucination": {
            "bad": sum(r["halluc"]["bad"] for r in results),
            "checked": sum(r["halluc"]["checked"] for r in results),
        },
        "gap": {"hit": sum(1 for r in gap if r["gap_reported"]), "total": len(gap)},
        "errors": sum(1 for r in results if r["status"] != "ok"),
        "all_pass": all(r["pass"] for r in results) if results else True,
    }


# ── 실행 기록 (eval/runs/ - --failed 의 원천) ───────────────────────────

def save_run(results: list[dict], runs_dir: Path | str = RUNS_DIR, partial: bool = False) -> Path:
    """run_<ts>.json 저장 + latest.json 갱신. 부분 실행은 latest 에 pr_id 기준 병합."""
    runs_dir = Path(runs_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)

    merged = list(results)
    latest_p = runs_dir / "latest.json"
    if partial and latest_p.is_file():
        prev = {r["pr_id"]: r for r in json.loads(latest_p.read_text(encoding="utf-8"))["results"]}
        prev.update({r["pr_id"]: r for r in results})
        merged = [prev[k] for k in sorted(prev)]

    payload = {
        "contracts_version": SCHEMA_VERSION,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "partial": partial,
        "executed": [r["pr_id"] for r in results],
        "results": merged,
        "metrics": compute_metrics(merged),
    }
    blob = json.dumps(payload, ensure_ascii=False, indent=2)
    run_p = runs_dir / f"run_{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.json"
    run_p.write_text(blob, encoding="utf-8")
    latest_p.write_text(blob, encoding="utf-8")
    return run_p


def load_failed_ids(runs_dir: Path | str = RUNS_DIR) -> list[str]:
    latest_p = Path(runs_dir) / "latest.json"
    if not latest_p.is_file():
        raise FileNotFoundError("이전 실행 기록 없음 - 먼저 make eval 로 전체 실행 필요")
    data = json.loads(latest_p.read_text(encoding="utf-8"))
    return [r["pr_id"] for r in data["results"] if not r["pass"]]


# ── 표 리포트 ───────────────────────────────────────────────────────────

def _w(s: str) -> int:
    """터미널 표시 폭 (한글 등 동아시아 전각 = 2칸)."""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in s)


def _pad(s: str, width: int) -> str:
    return s + " " * max(0, width - _w(s))


def _row_of(r: dict) -> list[str]:
    expected = r["expected"]
    expected_s = "gap 보고" if expected == "gap" else (", ".join(expected) or "지적 없음")

    if r["status"] == "not_implemented":
        got_s, verdict = "미구현", "ERROR"
    elif r["status"] == "error":
        got_s, verdict = "ERROR", "ERROR"
    else:
        parts = []
        if r["predicted_violations"]:
            parts.append(", ".join(r["predicted_violations"]))
        if r["gap_reported"]:
            parts.append("gap 보고")
        got_s = " + ".join(parts) or "지적 없음"
        verdict = "PASS" if r["pass"] else "FAIL"

    checked = r["halluc"]["checked"]
    halluc_s = f"{r['halluc']['bad']}/{checked}" if checked else "-"

    notes = []
    if r["missing"]:
        notes.append("누락: " + ", ".join(r["missing"]))
    if r["extra"]:
        notes.append("추가 지적: " + ", ".join(r["extra"]))
    if r["fp_count"]:
        notes.append(f"오탐 {r['fp_count']}건")
    if r["gap_reported"] and not r["gap_expected"]:
        notes.append("gap 오보고")
    if r["gap_expected"] and not r["gap_reported"] and r["status"] == "ok":
        notes.append("gap 미보고")
    for v in r["halluc"]["details"]:
        notes.extend(v["reasons"])
    if r["error"]:
        notes.append(r["error"][:60])

    return [r["pr_id"], CATEGORY_KR[r["category"]], expected_s, got_s, halluc_s, verdict,
            "; ".join(notes)[:100]]


def _fmt_ratio(hit: int, total: int) -> str:
    pct = f" ({hit / total * 100:.0f}%)" if total else ""
    return f"{hit}/{total}{pct}"


def render_report(results: list[dict], metrics: dict) -> str:
    header = ["PR", "분류", "기대", "결과", "환각", "판정", "비고"]
    rows = [_row_of(r) for r in results]
    widths = [max(_w(h), *(_w(row[i]) for row in rows)) if rows else _w(h)
              for i, h in enumerate(header)]

    def line(cells: list[str]) -> str:
        return "  ".join(_pad(c, widths[i]) for i, c in enumerate(cells)).rstrip()

    d, fp, h, g = metrics["detection"], metrics["false_positive"], metrics["hallucination"], metrics["gap"]
    n_pass = sum(1 for r in results if r["pass"])
    out = [
        f"골든셋 평가 리포트 - {len(results)} 케이스 (contracts v{SCHEMA_VERSION})",
        "",
        line(header),
        line(["-" * w for w in widths]),
        *(line(row) for row in rows),
        "",
        "지표 (브리프 §4.2)",
        f"  탐지율          : {_fmt_ratio(d['hit'], d['total'])}",
        f"  오탐            : {fp['count']}건 (정상 PR {fp['normal_prs']}개 중 {fp['prs_with_fp']}개에서)",
        f"  환각률          : {_fmt_ratio(h['bad'], h['checked'])} - rule_id 실존 + rule_quote·evidence string-match",
        f"  지침공백 정확도 : {_fmt_ratio(g['hit'], g['total'])}",
        f"  전체 PASS       : {n_pass}/{len(results)}  |  에러 {metrics['errors']}건",
    ]
    return "\n".join(out)


# ── CLI ─────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    else:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(
        prog="python -m eval.harness",
        description="골든셋 평가 하네스 - 표 리포트 + 환각 자동검증 + 실행 기록(JSON)",
    )
    ap.add_argument("--only", help="특정 PR 만 실행 (예: pr_003 또는 pr_001,pr_004)")
    ap.add_argument("--failed", action="store_true", help="직전 실행(latest.json) 실패 케이스만 재실행")
    ap.add_argument("--golden-dir", default=str(GOLDEN_DIR), help=argparse.SUPPRESS)
    ap.add_argument("--corpus-dir", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--runs-dir", default=str(RUNS_DIR), help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    corpus_dir = Path(args.corpus_dir) if args.corpus_dir else _default_corpus_dir()
    corpus_idx = build_corpus_index(corpus_dir)
    cases = load_golden_cases(args.golden_dir)
    if not cases:
        print(f"[harness] golden/ 에 PR 케이스 없음 ({args.golden_dir}) - 세션 C 통합 전이면 정상입니다.")
        return 0

    partial = False
    if args.failed:
        try:
            failed = set(load_failed_ids(args.runs_dir))
        except FileNotFoundError as e:
            print(f"[harness] {e}")
            return 2
        if not failed:
            print("[harness] 직전 실행 실패 케이스 없음 - 전체 PASS 상태입니다.")
            return 0
        cases = [c for c in cases if c.pr_id in failed]
        partial = True
    elif args.only:
        wanted = {w.strip() for w in args.only.split(",") if w.strip()}
        unknown = wanted - {c.pr_id for c in cases}
        if unknown:
            print(f"[harness] golden/ 에 없는 PR: {', '.join(sorted(unknown))}")
            return 2
        cases = [c for c in cases if c.pr_id in wanted]
        partial = True

    if not corpus_idx:
        print(f"[harness] 경고: 코퍼스 비어 있음({corpus_dir}) - 모든 인용이 환각으로 집계됩니다.")

    try:
        from src.config import TEMPERATURE
        temp_note = f"temperature {TEMPERATURE} (src/config.py)"
    except Exception:
        temp_note = "temperature 0 (src/config.py 고정)"
    print(f"[harness] {len(cases)}개 케이스 실행 - {temp_note}, 규칙 {len(corpus_idx)}개\n")

    results = run_cases(cases, corpus_idx)
    run_path = save_run(results, args.runs_dir, partial=partial)

    print(render_report(results, compute_metrics(results)))
    if partial:
        lm = json.loads((Path(args.runs_dir) / "latest.json").read_text(encoding="utf-8"))["metrics"]
        print(
            f"\n누적(latest) 지표 - 탐지 {lm['detection']['hit']}/{lm['detection']['total']}"
            f", 오탐 {lm['false_positive']['count']}건"
            f", 환각 {lm['hallucination']['bad']}/{lm['hallucination']['checked']}"
            f", 지침공백 {lm['gap']['hit']}/{lm['gap']['total']}"
        )
    print(f"\n[harness] 실행 기록: {run_path}")

    failed_now = [r["pr_id"] for r in results if not r["pass"]]
    if failed_now:
        print(f"[harness] FAIL {len(failed_now)}건: {', '.join(failed_now)} - 재실행: make eval-failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
