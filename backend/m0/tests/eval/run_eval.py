"""
KMS 파이프라인 성숙도 평가 스크립트 v2

단순 Accuracy 측정을 넘어 파이프라인 성숙도(Maturity)를 4개 관점으로 평가한다.

  L1  : 파이프라인 성숙도 점수 (0 ~ 100)
  L2A : Accuracy   — stored 문서의 메타데이터 품질 (HITL 제외)
  L2B : Automation — 자동 완료율 / HITL 발생률 / 오류율
  L2C : Reliability — 문서 유형별 성공률 / 처리 시간

핵심 설계 원칙:
  - hitl_pending 문서는 Accuracy 계산에서 제외 (0점 왜곡 방지)
  - Accuracy 분모 = stored 문서만
  - Automation 분모 = 전체 문서
  - 엔티티 평가: Golden 10종 타입 → 파이프라인 3종 매핑 후 name recall + partial credit

사용법:
    uv run python tests/eval/run_eval.py --mode file
    uv run python tests/eval/run_eval.py --mode file --output results/report.md
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

EVAL_DIR = Path(__file__).parent
GOLDEN_PATH = EVAL_DIR / "golden_dataset.json"
RESULTS_DIR = EVAL_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# 엔티티 타입 매핑 — Golden v1(10종) → Pipeline 3종
# ---------------------------------------------------------------------------
# Golden Dataset은 세부 타입을 사용하지만 파이프라인은 3종만 추출한다.
# 이 매핑으로 Golden을 파이프라인 타입으로 그루핑해 fair comparison을 수행한다.

ENTITY_TYPE_MAP: dict[str, str] = {
    "technology":   "Technology",
    "tool":         "Technology",
    "product":      "Technology",
    "standard":     "Technology",
    "endpoint":     "Technology",
    "model":        "Technology",
    "methodology":  "Pattern",
    "process":      "Pattern",
    "concept":      "Concept",
    "role":         "Concept",
    "organization": "Concept",
    "metric":       "Concept",
    # 이미 파이프라인 타입으로 작성된 경우 그대로 통과
    "Technology":   "Technology",
    "Pattern":      "Pattern",
    "Concept":      "Concept",
}


# ---------------------------------------------------------------------------
# KPI 목표값 및 CI 게이트
# ---------------------------------------------------------------------------

ACCURACY_TARGETS: dict[str, float] = {
    "title_accuracy":           0.80,
    "category_accuracy":        0.85,
    "avg_tags_f1":              0.60,
    "avg_entity_name_recall":   0.60,
    "avg_quality_score":        0.85,
}

AUTOMATION_TARGETS: dict[str, float] = {
    "completion_rate": 0.90,   # ≥ 90%
    "hitl_rate":       0.15,   # ≤ 15% (상한)
    "error_rate":      0.05,   # ≤  5% (상한)
}

# CI 게이트: (operator, threshold)
# ">=" → 값이 threshold 이상이어야 PASS
# "<=" → 값이 threshold 이하이어야 PASS (hitl_rate, error_rate)
CI_GATE: dict[str, tuple[str, float]] = {
    "completion_rate":        (">=", 0.80),
    "category_accuracy":      (">=", 0.85),
    "avg_tags_f1":            (">=", 0.60),
    "avg_entity_name_recall": (">=", 0.60),
    "avg_quality_score":      (">=", 0.85),
}

# 성숙도 점수 가중치 (합 = 1.0)
MATURITY_WEIGHTS = {
    "automation": 0.40,
    "accuracy":   0.60,
}


# ---------------------------------------------------------------------------
# 데이터 모델
# ---------------------------------------------------------------------------

@dataclass
class GoldenEntry:
    id: str
    file: str
    file_type: str
    expected_title: Optional[str]
    expected_category: Optional[str]
    expected_tags: list[str]
    expected_entities: dict[str, list[str]]
    note: str = ""

    @property
    def expected_entities_mapped(self) -> dict[str, list[str]]:
        """Golden 세부 타입을 파이프라인 3종으로 그루핑."""
        mapped: dict[str, list[str]] = {}
        for raw_type, names in self.expected_entities.items():
            pipeline_type = ENTITY_TYPE_MAP.get(raw_type, "Concept")
            mapped.setdefault(pipeline_type, []).extend(names)
        return mapped

    @property
    def all_expected_entity_names(self) -> list[str]:
        return [n for names in self.expected_entities.values() for n in names]


@dataclass
class PipelineResult:
    doc_id: str
    golden_id: str
    title: Optional[str]
    category: Optional[str]
    tags: list[str]
    entities: dict[str, list[str]]
    quality_score: float = 0.0
    status: str = "unknown"
    file_type: str = "unknown"
    processing_time_ms: Optional[float] = None


@dataclass
class AccuracyResult:
    golden_id: str
    file_type: str
    title_match: bool
    category_match: bool
    tags_recall: float
    tags_precision: float
    entity_name_recall: float
    entity_partial_score: float
    quality_score: float
    status: str
    skipped: bool = False
    details: dict = field(default_factory=dict)

    @property
    def tags_f1(self) -> float:
        s = self.tags_recall + self.tags_precision
        return 0.0 if s == 0 else 2 * self.tags_recall * self.tags_precision / s


# ---------------------------------------------------------------------------
# 텍스트 정규화
# ---------------------------------------------------------------------------

def normalize_text(s: str) -> str:
    """공백·특수문자 제거 후 소문자 변환."""
    return re.sub(r"[\s\-_\(\)（）·]+", "", s.lower())


# ---------------------------------------------------------------------------
# 매칭 로직
# ---------------------------------------------------------------------------

def match_title(expected: Optional[str], actual: Optional[str]) -> bool:
    if not expected or not actual:
        return False
    return normalize_text(expected) == normalize_text(actual)


def compute_tags_metrics(
    expected: list[str], actual: list[str]
) -> tuple[float, float]:
    if not expected:
        return (1.0, 1.0) if not actual else (1.0, 0.0)
    if not actual:
        return (0.0, 0.0)
    exp_norm = {normalize_text(t) for t in expected}
    act_norm = {normalize_text(t) for t in actual}
    tp = len(exp_norm & act_norm)
    return tp / len(exp_norm), tp / len(act_norm)


def compute_entity_metrics(
    golden: GoldenEntry, result: PipelineResult
) -> tuple[float, float]:
    """
    Returns:
        entity_name_recall   : 이름 기준 재현율 (타입 무관)
        entity_partial_score : 이름+타입 일치 → 1.0 / 이름만 일치 → 0.5
    """
    all_expected = golden.all_expected_entity_names
    if not all_expected:
        return 1.0, 1.0

    actual_all = {
        normalize_text(n)
        for names in result.entities.values()
        for n in names
    }

    # 이름 재현율 (타입 무관)
    matched = sum(1 for n in all_expected if normalize_text(n) in actual_all)
    name_recall = matched / len(all_expected)

    # Partial credit (타입 일치 보너스)
    mapped = golden.expected_entities_mapped
    partial_total = 0.0
    for p_type, exp_names in mapped.items():
        act_type_names = {normalize_text(n) for n in result.entities.get(p_type, [])}
        for n in exp_names:
            n_norm = normalize_text(n)
            if n_norm in act_type_names:
                partial_total += 1.0
            elif n_norm in actual_all:
                partial_total += 0.5
    partial_score = partial_total / len(all_expected)

    return name_recall, partial_score


# ---------------------------------------------------------------------------
# 문서 단위 평가
# ---------------------------------------------------------------------------

def evaluate_document(
    golden: GoldenEntry, result: Optional[PipelineResult]
) -> AccuracyResult:
    base = AccuracyResult(
        golden_id=golden.id,
        file_type=golden.file_type,
        title_match=False,
        category_match=False,
        tags_recall=0.0,
        tags_precision=0.0,
        entity_name_recall=0.0,
        entity_partial_score=0.0,
        quality_score=result.quality_score if result else 0.0,
        status=result.status if result else "not_found",
        details={
            "expected_title":    golden.expected_title,
            "actual_title":      result.title if result else None,
            "expected_category": golden.expected_category,
            "actual_category":   result.category if result else None,
            "expected_tags":     golden.expected_tags,
            "actual_tags":       result.tags if result else [],
        },
    )

    # stored 이외 (hitl_pending / error / not_found)는 Accuracy 계산 제외
    if not result or result.status != "stored":
        base.skipped = True
        return base

    e_recall, e_partial = compute_entity_metrics(golden, result)
    t_recall, t_precision = compute_tags_metrics(golden.expected_tags, result.tags)

    base.title_match          = match_title(golden.expected_title, result.title)
    base.category_match       = golden.expected_category == result.category
    base.tags_recall          = t_recall
    base.tags_precision       = t_precision
    base.entity_name_recall   = e_recall
    base.entity_partial_score = e_partial
    base.skipped              = False
    return base


# ---------------------------------------------------------------------------
# KPI 계층 계산
# ---------------------------------------------------------------------------

def compute_automation_kpis(all_results: list[PipelineResult]) -> dict:
    """L2B: 자동화율 KPI — 전체 문서 기준."""
    total = len(all_results)
    if not total:
        return {"error": "결과 없음"}

    by_status: dict[str, int] = {}
    for r in all_results:
        by_status[r.status] = by_status.get(r.status, 0) + 1

    stored  = by_status.get("stored", 0)
    partial = by_status.get("stored_partial", 0)
    hitl    = by_status.get("hitl_pending", 0)
    error   = by_status.get("error", 0) + by_status.get("timeout", 0) + by_status.get("failed", 0)

    # Stage별 HITL 분포를 추후 run_pipeline.py에서 hitl_stage 필드 추가 시 확장 가능
    return {
        "total_documents":  total,
        "stored":           stored,
        "stored_partial":   partial,
        "hitl_pending":     hitl,
        "error_or_timeout": error,
        "completion_rate":  (stored + partial) / total,
        "hitl_rate":        hitl / total,
        "error_rate":       error / total,
        "status_breakdown": by_status,
    }


def compute_accuracy_kpis(eval_results: list[AccuracyResult]) -> dict:
    """L2A: 메타데이터 정확도 KPI — stored 문서만."""
    stored = [r for r in eval_results if not r.skipped]
    if not stored:
        return {"evaluated_documents": 0, "note": "stored 문서 없음 — Accuracy 계산 불가"}

    has_golden = [r for r in stored if r.details.get("expected_title") is not None]

    kpis: dict = {
        "evaluated_documents":    len(stored),
        "documents_with_golden":  len(has_golden),
        "avg_quality_score":      _avg(r.quality_score for r in stored),
    }

    if has_golden:
        kpis.update({
            "title_accuracy":           _avg(r.title_match for r in has_golden),
            "category_accuracy":        _avg(r.category_match for r in has_golden),
            "avg_tags_recall":          _avg(r.tags_recall for r in has_golden),
            "avg_tags_precision":       _avg(r.tags_precision for r in has_golden),
            "avg_tags_f1":              _avg(r.tags_f1 for r in has_golden),
            "avg_entity_name_recall":   _avg(r.entity_name_recall for r in has_golden),
            "avg_entity_partial_score": _avg(r.entity_partial_score for r in has_golden),
        })

    # 파일 유형별 정확도
    by_type: dict[str, list[AccuracyResult]] = {}
    for r in has_golden:
        by_type.setdefault(r.file_type, []).append(r)

    kpis["by_file_type"] = {
        ft: {
            "count":                  len(rs),
            "title_accuracy":         _avg(r.title_match for r in rs),
            "category_accuracy":      _avg(r.category_match for r in rs),
            "avg_tags_f1":            _avg(r.tags_f1 for r in rs),
            "avg_entity_name_recall": _avg(r.entity_name_recall for r in rs),
        }
        for ft, rs in by_type.items()
    }

    return kpis


def compute_reliability_kpis(all_results: list[PipelineResult]) -> dict:
    """L2C: 안정성 KPI — 유형별 성공률 / 처리 시간."""
    by_type: dict[str, list[PipelineResult]] = {}
    for r in all_results:
        by_type.setdefault(r.file_type, []).append(r)

    type_stats = {
        ft: {
            "total":        len(rs),
            "stored":       sum(1 for r in rs if r.status == "stored"),
            "hitl_pending": sum(1 for r in rs if r.status == "hitl_pending"),
            "error":        sum(1 for r in rs if r.status in ("error", "timeout", "failed")),
            "success_rate": sum(1 for r in rs if r.status == "stored") / len(rs),
        }
        for ft, rs in by_type.items()
    }

    timing = [r.processing_time_ms for r in all_results if r.processing_time_ms]
    timing_stats: dict = {}
    if timing:
        timing_stats = {
            "count":   len(timing),
            "avg_ms":  round(sum(timing) / len(timing)),
            "max_ms":  round(max(timing)),
            "min_ms":  round(min(timing)),
        }

    return {"by_file_type": type_stats, "timing": timing_stats}


def compute_maturity_score(automation: dict, accuracy: dict) -> float:
    """
    L1: 파이프라인 성숙도 점수 (0 ~ 100).

    automation 40% : completion_rate
    accuracy   60% : category + entity_name_recall + tags_f1 + quality 균등 평균
    """
    auto_score = automation.get("completion_rate", 0) * 100

    acc_keys = [
        "category_accuracy", "avg_entity_name_recall",
        "avg_tags_f1", "avg_quality_score",
    ]
    acc_vals = [accuracy[k] for k in acc_keys if k in accuracy]
    acc_score = (sum(acc_vals) / len(acc_vals) * 100) if acc_vals else 0

    return round(
        MATURITY_WEIGHTS["automation"] * auto_score
        + MATURITY_WEIGHTS["accuracy"] * acc_score,
        1,
    )


def _evaluate_ci_gate(automation: dict, accuracy: dict) -> dict:
    merged = {**automation, **accuracy}
    details: dict[str, dict] = {}
    for key, (op, threshold) in CI_GATE.items():
        val = merged.get(key)
        if val is None:
            details[key] = {"status": "N/A", "value": None, "threshold": threshold}
            continue
        passed = val >= threshold if op == ">=" else val <= threshold
        details[key] = {
            "status":    "PASS" if passed else "FAIL",
            "value":     round(float(val), 4),
            "threshold": threshold,
        }
    overall = "PASS" if all(v["status"] in ("PASS", "N/A") for v in details.values()) else "FAIL"
    return {"overall": overall, "details": details}


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

def _avg(values) -> float:
    vals = list(values)
    return sum(vals) / len(vals) if vals else 0.0


# ---------------------------------------------------------------------------
# 데이터 로더
# ---------------------------------------------------------------------------

def load_golden_dataset() -> list[GoldenEntry]:
    data = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    return [
        GoldenEntry(
            id=doc["id"],
            file=doc["file"],
            file_type=doc["file_type"],
            expected_title=doc.get("expected", {}).get("title"),
            expected_category=doc.get("expected", {}).get("category"),
            expected_tags=doc.get("expected", {}).get("tags", []),
            expected_entities=doc.get("expected", {}).get("entities", {}),
            note=doc.get("expected", {}).get("note", ""),
        )
        for doc in data["documents"]
    ]


def load_results_from_file(results_path: Path) -> dict[str, PipelineResult]:
    data = json.loads(results_path.read_text(encoding="utf-8"))
    out: dict[str, PipelineResult] = {}
    for item in data:
        r = PipelineResult(
            doc_id=item.get("doc_id", ""),
            golden_id=item.get("golden_id", ""),
            title=item.get("title"),
            category=item.get("category"),
            tags=item.get("tags", []),
            entities=item.get("entities", {}),
            quality_score=float(item.get("quality_score") or 0.0),
            status=item.get("status", "unknown"),
            file_type=item.get("file_type", "unknown"),
            processing_time_ms=item.get("processing_time_ms"),
        )
        out[item.get("golden_id", r.doc_id)] = r
    return out


# ---------------------------------------------------------------------------
# 리포트 생성
# ---------------------------------------------------------------------------

def render_markdown_report(
    eval_results: list[AccuracyResult],
    automation: dict,
    accuracy: dict,
    reliability: dict,
    maturity_score: float,
    output_path: Path,
) -> None:
    import datetime
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    total = automation.get("total_documents", 0)
    evaluated = accuracy.get("evaluated_documents", 0)

    lines = [
        "# KMS 파이프라인 성숙도 평가 보고서",
        "",
        f"**평가 일시**: {now}  ",
        f"**전체 문서**: {total}개  |  **Accuracy 평가 대상(stored)**: {evaluated}개",
        "",
        f"## 📊 파이프라인 성숙도 점수: **{maturity_score} / 100**",
        "",
        "> 성숙도 = Automation 40% + Accuracy 60%",
        "> Accuracy 분모 = stored 문서만 (HITL 제외)",
        "",
        "---",
        "",
        "## L2A. 메타데이터 정확도 (Accuracy)",
        "",
        f"평가 대상: **{evaluated}개** (stored) / 전체 {total}개",
        "",
        "| KPI | 값 | 목표 | 달성 |",
        "|----|-----|------|------|",
    ]

    acc_labels = {
        "title_accuracy":           "제목 정확도",
        "category_accuracy":        "카테고리 정확도",
        "avg_tags_f1":              "태그 F1",
        "avg_entity_name_recall":   "엔티티 이름 재현율 (Name Recall)",
        "avg_entity_partial_score": "엔티티 Partial Score (이름+타입)",
        "avg_quality_score":        "파싱 품질 점수",
    }
    for key, label in acc_labels.items():
        val = accuracy.get(key)
        if val is None:
            continue
        target = ACCURACY_TARGETS.get(key)
        ok = ("OK" if val >= target else "!!") if target else "-"
        target_str = f"{target:.2f}" if target else "-"
        lines.append(f"| {label} | {val:.3f} | {target_str} | {ok} |")

    by_type = accuracy.get("by_file_type", {})
    if by_type:
        lines += [
            "",
            "### 파일 유형별 정확도",
            "",
            "| 유형 | 수 | 제목 | 카테고리 | 태그 F1 | 엔티티 Recall |",
            "|-----|---|------|---------|--------|------------|",
        ]
        for ft, s in sorted(by_type.items()):
            lines.append(
                f"| {ft.upper()} | {s['count']} "
                f"| {s['title_accuracy']:.2f} | {s['category_accuracy']:.2f} "
                f"| {s['avg_tags_f1']:.2f} | {s['avg_entity_name_recall']:.2f} |"
            )

    # L2B Automation
    lines += [
        "", "---", "",
        "## L2B. 자동화율 (Automation)",
        "",
        "| KPI | 값 | 목표 | 달성 |",
        "|----|-----|------|------|",
    ]
    auto_labels = {
        "completion_rate": ("자동 완료율 (stored / total)", ">="),
        "hitl_rate":       ("HITL 발생률",                  "<="),
        "error_rate":      ("오류율",                       "<="),
    }
    for key, (label, op) in auto_labels.items():
        val = automation.get(key, 0)
        target = AUTOMATION_TARGETS[key]
        ok = "✅" if (val >= target if op == ">=" else val <= target) else "❌"
        lines.append(f"| {label} | {val:.1%} | {target:.0%} | {ok} |")

    breakdown = automation.get("status_breakdown", {})
    if breakdown:
        lines += ["", "**상태별 분포**"]
        for s, cnt in sorted(breakdown.items()):
            pct = cnt / total * 100 if total else 0
            lines.append(f"- `{s}`: {cnt}개 ({pct:.0f}%)")

    # L2C Reliability
    lines += ["", "---", "", "## L2C. 안정성 (Reliability)", ""]
    rel_by_type = reliability.get("by_file_type", {})
    if rel_by_type:
        lines += [
            "| 유형 | 전체 | Stored | HITL | Error | 성공률 |",
            "|-----|------|--------|------|-------|-------|",
        ]
        for ft, s in sorted(rel_by_type.items()):
            lines.append(
                f"| {ft.upper()} | {s['total']} | {s['stored']} "
                f"| {s['hitl_pending']} | {s['error']} | {s['success_rate']:.0%} |"
            )

    timing = reliability.get("timing", {})
    if timing:
        lines += [
            "",
            f"**처리 시간** (n={timing['count']}):  "
            f"평균 {timing['avg_ms']}ms / 최대 {timing['max_ms']}ms / 최소 {timing['min_ms']}ms",
        ]

    # 문서별 상세
    lines += [
        "", "---", "",
        "## 문서별 상세 결과",
        "",
        "| 문서 | 유형 | 상태 | 제목 ✓ | 카테고리 ✓ | 태그 F1 | 엔티티 Recall | 파싱 품질 |",
        "|-----|------|------|--------|-----------|--------|-------------|---------|",
    ]
    for r in eval_results:
        if r.skipped:
            t_icon = c_icon = "➖"
            tags_f1 = entity_recall = quality = "—"
        else:
            t_icon = "✅" if r.title_match else "❌"
            c_icon = "✅" if r.category_match else "❌"
            tags_f1 = f"{r.tags_f1:.2f}"
            entity_recall = f"{r.entity_name_recall:.2f}"
            quality = f"{r.quality_score:.2f}"
        lines.append(
            f"| {r.golden_id} | {r.file_type.upper()} | {r.status} "
            f"| {t_icon} | {c_icon} | {tags_f1} | {entity_recall} | {quality} |"
        )

    # 오류 분석 (stored 중 미달 항목)
    failures = [
        r for r in eval_results
        if not r.skipped and (not r.title_match or not r.category_match or r.tags_f1 < 0.4)
    ]
    skipped = [r for r in eval_results if r.skipped]
    if failures or skipped:
        lines += ["", "---", "", "## 오류 및 제외 분석", ""]

    for r in skipped:
        lines += [f"### ➖ {r.golden_id} — `{r.status}` (Accuracy 평가 제외)", ""]

    for r in failures:
        lines += [
            f"### ❌ {r.golden_id}",
            f"- **기대 제목**: {r.details.get('expected_title', 'N/A')}",
            f"- **실제 제목**: {r.details.get('actual_title', 'N/A')}",
            f"- **기대 카테고리**: {r.details.get('expected_category', 'N/A')}",
            f"- **실제 카테고리**: {r.details.get('actual_category', 'N/A')}",
            f"- **기대 태그**: {', '.join(r.details.get('expected_tags', []))}",
            f"- **실제 태그**: {', '.join(r.details.get('actual_tags', []))}",
            "",
        ]

    output_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("보고서 저장: %s", output_path)


def save_json_report(
    automation: dict,
    accuracy: dict,
    reliability: dict,
    maturity_score: float,
    ci_result: dict,
    output_path: Path,
) -> None:
    """CI/CD 연동용 구조화 JSON 리포트."""
    import datetime
    report = {
        "timestamp":     datetime.datetime.now().isoformat(),
        "maturity_score": maturity_score,
        "ci_gate":       ci_result,
        "automation":    automation,
        "accuracy":      accuracy,
        "reliability":   reliability,
    }
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("JSON 리포트 저장: %s", output_path)


# ---------------------------------------------------------------------------
# 콘솔 출력
# ---------------------------------------------------------------------------

def print_summary(
    automation: dict,
    accuracy: dict,
    maturity_score: float,
    ci_result: dict,
) -> None:
    total = automation.get("total_documents", 0)
    evaluated = accuracy.get("evaluated_documents", 0)

    print(f"\n{'='*54}")
    print(f"  KMS 파이프라인 성숙도 점수: {maturity_score:5.1f} / 100")
    print(f"{'='*54}")
    print(f"\n[L2A Accuracy]  stored {evaluated}개 / 전체 {total}개 기준")
    for key, target in ACCURACY_TARGETS.items():
        val = accuracy.get(key)
        if val is None:
            print(f"  [ ] {key}: N/A")
            continue
        icon = "[OK]" if val >= target else "[!!]"
        print(f"  {icon} {key}: {val:.3f}  (목표 {target:.2f})")

    print(f"\n[L2B Automation]  전체 {total}개 기준")
    for key, (label, op) in {
        "completion_rate": ("완료율",  ">="),
        "hitl_rate":       ("HITL율", "<="),
        "error_rate":      ("오류율", "<="),
    }.items():
        val = automation.get(key, 0)
        target = AUTOMATION_TARGETS[key]
        ok = val >= target if op == ">=" else val <= target
        icon = "[OK]" if ok else "[!!]"
        op_sym = ">=" if op == ">=" else "<="
        print(f"  {icon} {label}: {val:.1%}  (목표 {op_sym}{target:.0%})")

    print(f"\n[CI Gate]  {ci_result['overall']}")
    for key, v in ci_result["details"].items():
        if v["status"] == "N/A":
            icon = "[ ]"
        elif v["status"] == "PASS":
            icon = "[OK]"
        else:
            icon = "[!!]"
        val_str = f"{v['value']:.3f}" if v["value"] is not None else "N/A"
        print(f"  {icon} {key}: {val_str}  (임계값 {v['threshold']:.2f})")
    print()


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="KMS 파이프라인 성숙도 평가")
    parser.add_argument("--mode", choices=["file", "db"], default="file")
    parser.add_argument("--results", type=Path, default=RESULTS_DIR / "pipeline_output.json")
    parser.add_argument("--doc-id", nargs="*")
    parser.add_argument("--output",      type=Path, default=RESULTS_DIR / "report.md")
    parser.add_argument("--json-output", type=Path, default=RESULTS_DIR / "report.json")
    args = parser.parse_args()

    golden_entries = load_golden_dataset()
    if args.doc_id:
        golden_entries = [g for g in golden_entries if g.id in args.doc_id]
        logger.info("필터링된 문서: %s", [g.id for g in golden_entries])

    evaluable = [g for g in golden_entries if g.expected_title is not None or g.expected_tags]
    skip_count = len(golden_entries) - len(evaluable)
    if skip_count:
        logger.info("%d개 문서는 golden 미완성 — 스킵", skip_count)

    if not args.results.exists():
        logger.error("결과 파일 없음: %s", args.results)
        sys.exit(1)

    pipeline_results = load_results_from_file(args.results)
    all_results      = list(pipeline_results.values())

    eval_results = [
        evaluate_document(g, pipeline_results.get(g.id))
        for g in evaluable
    ]

    # KPI 계산
    automation  = compute_automation_kpis(all_results)
    accuracy    = compute_accuracy_kpis(eval_results)
    reliability = compute_reliability_kpis(all_results)
    maturity    = compute_maturity_score(automation, accuracy)
    ci_result   = _evaluate_ci_gate(automation, accuracy)

    # 출력
    print_summary(automation, accuracy, maturity, ci_result)
    render_markdown_report(eval_results, automation, accuracy, reliability, maturity, args.output)
    save_json_report(automation, accuracy, reliability, maturity, ci_result, args.json_output)

    if ci_result["overall"] == "FAIL":
        failed = [k for k, v in ci_result["details"].items() if v["status"] == "FAIL"]
        logger.warning("CI 게이트 실패: %s", failed)
        sys.exit(1)


if __name__ == "__main__":
    main()
