"""
KMS 파이프라인 평가 스크립트

Golden Dataset과 파이프라인 실행 결과를 비교하여 KPI를 산출한다.

사용법:
    # 전체 평가 실행 (실제 DB에서 결과 조회)
    uv run python tests/eval/run_eval.py --mode db

    # 로컬 JSON 결과 파일과 비교
    uv run python tests/eval/run_eval.py --mode file --results tests/eval/results/pipeline_output.json

    # 특정 문서만 평가
    uv run python tests/eval/run_eval.py --doc-id md_01 md_02
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

# KPI 목표값 — 리포트 표시와 CI exit-code 판정에 동일하게 사용
KPI_TARGETS: dict[str, float] = {
    "title_accuracy": 0.80,
    "category_accuracy": 0.85,
    "avg_tags_recall": 0.70,
    "avg_tags_precision": 0.50,
    "avg_tags_f1": 0.60,
    "avg_entities_recall": 0.60,
    "avg_quality_score": 0.85,
}

# CI 게이트: 이 KPI들이 목표 미달이면 exit(1)
CI_GATE_KPIS = {"title_accuracy", "category_accuracy", "avg_tags_f1", "avg_entities_recall", "avg_quality_score"}


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


@dataclass
class PipelineResult:
    doc_id: str
    title: Optional[str]
    category: Optional[str]
    tags: list[str]
    entities: dict[str, list[str]]
    quality_score: float = 0.0
    status: str = "unknown"


@dataclass
class DocEvalResult:
    golden_id: str
    file: str
    file_type: str
    title_match: bool
    category_match: bool
    tags_recall: float
    tags_precision: float
    entities_recall: float
    quality_score: float
    status: str
    details: dict = field(default_factory=dict)

    @property
    def tags_f1(self) -> float:
        if self.tags_recall + self.tags_precision == 0:
            return 0.0
        return 2 * self.tags_recall * self.tags_precision / (self.tags_recall + self.tags_precision)


# ---------------------------------------------------------------------------
# 평가 로직
# ---------------------------------------------------------------------------

def normalize_text(s: str) -> str:
    """공백/특수문자 정규화 및 소문자 변환."""
    return re.sub(r"[\s\-_\(\)（）]+", "", s.lower())


def title_match(expected: Optional[str], actual: Optional[str]) -> bool:
    if expected is None or actual is None:
        return False
    return normalize_text(expected) == normalize_text(actual)


def tags_metrics(
    expected: list[str],
    actual: list[str],
) -> tuple[float, float]:
    """태그 recall과 precision을 계산한다."""
    if not expected:
        return (1.0, 1.0) if not actual else (1.0, 0.0)
    if not actual:
        return (0.0, 0.0)

    expected_norm = {normalize_text(t) for t in expected}
    actual_norm = {normalize_text(t) for t in actual}

    tp = len(expected_norm & actual_norm)
    recall = tp / len(expected_norm)
    precision = tp / len(actual_norm)
    return recall, precision


def entities_recall(
    expected: dict[str, list[str]],
    actual: dict[str, list[str]],
) -> float:
    """기대 엔티티 중 실제로 추출된 비율."""
    all_expected = [
        normalize_text(e)
        for entities in expected.values()
        for e in entities
    ]
    if not all_expected:
        return 1.0

    all_actual = {
        normalize_text(e)
        for entities in actual.values()
        for e in entities
    }

    matched = sum(1 for e in all_expected if e in all_actual)
    return matched / len(all_expected)


def evaluate_document(
    golden: GoldenEntry,
    result: Optional[PipelineResult],
) -> DocEvalResult:
    if result is None:
        return DocEvalResult(
            golden_id=golden.id,
            file=golden.file,
            file_type=golden.file_type,
            title_match=False,
            category_match=False,
            tags_recall=0.0,
            tags_precision=0.0,
            entities_recall=0.0,
            quality_score=0.0,
            status="not_found",
        )

    t_match = title_match(golden.expected_title, result.title)
    c_match = golden.expected_category == result.category
    t_recall, t_precision = tags_metrics(golden.expected_tags, result.tags)
    e_recall = entities_recall(golden.expected_entities, result.entities)

    return DocEvalResult(
        golden_id=golden.id,
        file=golden.file,
        file_type=golden.file_type,
        title_match=t_match,
        category_match=c_match,
        tags_recall=t_recall,
        tags_precision=t_precision,
        entities_recall=e_recall,
        quality_score=result.quality_score,
        status=result.status,
        details={
            "expected_title": golden.expected_title,
            "actual_title": result.title,
            "expected_category": golden.expected_category,
            "actual_category": result.category,
            "expected_tags": golden.expected_tags,
            "actual_tags": result.tags,
        },
    )


# ---------------------------------------------------------------------------
# 결과 로더
# ---------------------------------------------------------------------------

def load_golden_dataset() -> list[GoldenEntry]:
    data = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    entries = []
    for doc in data["documents"]:
        expected = doc.get("expected", {})
        entries.append(GoldenEntry(
            id=doc["id"],
            file=doc["file"],
            file_type=doc["file_type"],
            expected_title=expected.get("title"),
            expected_category=expected.get("category"),
            expected_tags=expected.get("tags", []),
            expected_entities=expected.get("entities", {}),
            note=expected.get("note", ""),
        ))
    return entries


def load_results_from_file(results_path: Path) -> dict[str, PipelineResult]:
    data = json.loads(results_path.read_text(encoding="utf-8"))
    results: dict[str, PipelineResult] = {}
    for item in data:
        r = PipelineResult(
            doc_id=item["doc_id"],
            title=item.get("title"),
            category=item.get("category"),
            tags=item.get("tags", []),
            entities=item.get("entities", {}),
            quality_score=item.get("quality_score", 0.0),
            status=item.get("status", "unknown"),
        )
        results[item.get("golden_id", r.doc_id)] = r
    return results


async def load_results_from_db(doc_ids: list[str]) -> dict[str, PipelineResult]:
    """실제 DB에서 파이프라인 결과를 조회한다."""
    try:
        import asyncpg
        from shared.config import get_settings
    except ImportError:
        logger.warning("DB 접속 불가 — 빈 결과 반환. '--mode file'로 파일 기반 평가 사용 권장.")
        return {}

    settings = get_settings()
    conn = await asyncpg.connect(settings.database_url)
    try:
        rows = await conn.fetch("""
            SELECT d.id, d.title, d.category, d.status,
                   array_agg(DISTINCT dt.tag) FILTER (WHERE dt.tag IS NOT NULL) as tags,
                   d.quality_score
            FROM documents d
            LEFT JOIN document_tags dt ON d.id = dt.doc_id
            GROUP BY d.id, d.title, d.category, d.status, d.quality_score
            LIMIT 100
        """)
    finally:
        await conn.close()

    results: dict[str, PipelineResult] = {}
    for row in rows:
        results[str(row["id"])] = PipelineResult(
            doc_id=str(row["id"]),
            title=row["title"],
            category=row["category"],
            tags=row["tags"] or [],
            entities={},
            quality_score=float(row["quality_score"] or 0),
            status=row["status"],
        )
    return results


# ---------------------------------------------------------------------------
# 리포트 생성
# ---------------------------------------------------------------------------

def compute_kpis(eval_results: list[DocEvalResult]) -> dict:
    completed = [r for r in eval_results if r.status not in ("not_found", "unknown")]
    if not completed:
        return {"error": "평가 가능한 결과 없음"}

    has_golden = [r for r in completed if r.details.get("expected_title") is not None]

    return {
        "total_documents": len(eval_results),
        "completed": len(completed),
        "title_accuracy": sum(1 for r in has_golden if r.title_match) / len(has_golden) if has_golden else 0,
        "category_accuracy": sum(1 for r in has_golden if r.category_match) / len(has_golden) if has_golden else 0,
        "avg_tags_recall": sum(r.tags_recall for r in has_golden) / len(has_golden) if has_golden else 0,
        "avg_tags_precision": sum(r.tags_precision for r in has_golden) / len(has_golden) if has_golden else 0,
        "avg_tags_f1": sum(r.tags_f1 for r in has_golden) / len(has_golden) if has_golden else 0,
        "avg_entities_recall": sum(r.entities_recall for r in has_golden) / len(has_golden) if has_golden else 0,
        "avg_quality_score": sum(r.quality_score for r in completed) / len(completed),
    }


def render_report(
    eval_results: list[DocEvalResult],
    kpis: dict,
    output_path: Path,
) -> None:
    lines = [
        "# KMS 파이프라인 평가 보고서",
        "",
        f"**평가 일시**: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**총 문서 수**: {kpis.get('total_documents', 0)}",
        f"**평가 완료**: {kpis.get('completed', 0)}",
        "",
        "---",
        "",
        "## KPI 요약",
        "",
        "| 지표 | 값 | 목표 | 달성 |",
        "|------|----|------|------|",
    ]

    targets = KPI_TARGETS

    labels = {
        "title_accuracy": "제목 정확도",
        "category_accuracy": "카테고리 정확도",
        "avg_tags_recall": "태그 Recall (평균)",
        "avg_tags_precision": "태그 Precision (평균)",
        "avg_tags_f1": "태그 F1 (평균)",
        "avg_entities_recall": "엔티티 Recall (평균)",
        "avg_quality_score": "파싱 품질 점수 (평균)",
    }

    for key, label in labels.items():
        val = kpis.get(key, 0)
        target = targets.get(key, 0)
        achieved = "✅" if val >= target else "❌"
        lines.append(f"| {label} | {val:.3f} | {target:.2f} | {achieved} |")

    lines += ["", "---", "", "## 문서별 평가 결과", ""]
    lines += ["| 문서 ID | 파일 | 제목 | 카테고리 | 태그 F1 | 엔티티 Recall | 파싱 품질 | 상태 |",
              "|---------|------|------|---------|---------|--------------|---------|------|"]

    for r in eval_results:
        title_icon = "✅" if r.title_match else "❌"
        cat_icon = "✅" if r.category_match else "❌"
        lines.append(
            f"| {r.golden_id} | {Path(r.file).name} | {title_icon} | {cat_icon} "
            f"| {r.tags_f1:.2f} | {r.entities_recall:.2f} | {r.quality_score:.2f} | {r.status} |"
        )

    lines += ["", "---", "", "## 상세 오류 분석", ""]
    for r in eval_results:
        if not r.title_match or not r.category_match or r.tags_f1 < 0.5:
            lines += [
                f"### {r.golden_id} — {Path(r.file).name}",
                "",
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


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="KMS 파이프라인 평가")
    parser.add_argument("--mode", choices=["file", "db"], default="file")
    parser.add_argument("--results", type=Path, default=RESULTS_DIR / "pipeline_output.json")
    parser.add_argument("--doc-id", nargs="*", help="평가할 문서 ID 목록 (생략 시 전체)")
    parser.add_argument("--output", type=Path, default=RESULTS_DIR / "report.md")
    args = parser.parse_args()

    golden_entries = load_golden_dataset()

    if args.doc_id:
        golden_entries = [g for g in golden_entries if g.id in args.doc_id]
        logger.info("필터링된 문서: %s", [g.id for g in golden_entries])

    # golden이 없는(note만 있는) 항목은 평가 스킵
    evaluable = [g for g in golden_entries if g.expected_title is not None or g.expected_tags]
    skip_count = len(golden_entries) - len(evaluable)
    if skip_count:
        logger.info("%d개 문서는 golden 미완성 — 스킵", skip_count)

    if args.mode == "file":
        if not args.results.exists():
            logger.error("결과 파일 없음: %s", args.results)
            sys.exit(1)
        pipeline_results = load_results_from_file(args.results)
    else:
        import asyncio
        pipeline_results = asyncio.run(
            load_results_from_db([g.id for g in evaluable])
        )

    eval_results = [
        evaluate_document(g, pipeline_results.get(g.id))
        for g in evaluable
    ]

    kpis = compute_kpis(eval_results)

    print("\n=== KPI 요약 ===")
    for k, v in kpis.items():
        print(f"  {k}: {v:.3f}" if isinstance(v, float) else f"  {k}: {v}")

    render_report(eval_results, kpis, args.output)

    # 핵심 KPI 미달 시 exit code 1
    failed_kpis = [
        k for k in CI_GATE_KPIS
        if isinstance(kpis.get(k), float) and kpis[k] < KPI_TARGETS[k]
    ]
    if failed_kpis:
        logger.warning("핵심 KPI 미달: %s", failed_kpis)
        sys.exit(1)


if __name__ == "__main__":
    main()
