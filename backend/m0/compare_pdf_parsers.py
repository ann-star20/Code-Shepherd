"""
PDF 파서 성능 비교: PyMuPDF (현재) vs Marker (ML 기반)

대상: pdf_03_complex.pdf
출력: tests/eval/results/parser_comparison/ 에 각 파서 결과 저장 + 구조 지표 비교

사용:
    /app/.venv/bin/python compare_pdf_parsers.py
    /app/.venv/bin/python compare_pdf_parsers.py --skip-stage2   # Stage 2 평가 생략
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

PDF_PATH = Path(__file__).parent / "tests/eval/documents/pdf/pdf_03_complex.pdf"
OUT_DIR  = Path(__file__).parent / "tests/eval/results/parser_comparison"
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# 구조 지표 측정
# ---------------------------------------------------------------------------

def measure_structure(md: str) -> dict:
    lines = md.splitlines()
    h1 = sum(1 for l in lines if l.startswith("# ")  and not l.startswith("## "))
    h2 = sum(1 for l in lines if l.startswith("## ") and not l.startswith("### "))
    h3 = sum(1 for l in lines if l.startswith("### "))
    table_rows = sum(1 for l in lines if l.strip().startswith("|") and "|" in l[1:])
    table_sep  = sum(1 for l in lines if set(l.replace("|","").replace("-","").replace(" ","")) == set())
    tables_approx = max(0, table_sep)  # 구분선 수 ≈ 표 수 (근사)
    blanks = sum(1 for l in lines if not l.strip())
    return {
        "chars":        len(md),
        "lines":        len(lines),
        "blank_lines":  blanks,
        "h1":           h1,
        "h2":           h2,
        "h3":           h3,
        "headings":     h1 + h2 + h3,
        "table_rows":   table_rows,
        "table_seps":   tables_approx,
        "image_tags":   md.count("<!-- Image -->") + md.count("!["),
    }


# ---------------------------------------------------------------------------
# 파서 1: PyMuPDF (현재 Stage 1 코드 재사용)
# ---------------------------------------------------------------------------

def parse_with_pymupdf() -> tuple[str, float]:
    sys.path.insert(0, str(Path(__file__).parent))
    from app.pipeline.stage1_document_parser_agent import _convert_pdf_with_pymupdf
    t0 = time.perf_counter()
    md, image_ratio = _convert_pdf_with_pymupdf(str(PDF_PATH))
    elapsed = time.perf_counter() - t0
    return md, image_ratio, elapsed


# ---------------------------------------------------------------------------
# 파서 2: Marker (ML 레이아웃 모델)
# ---------------------------------------------------------------------------

def parse_with_marker() -> tuple[str, float]:
    print("  Marker 모델 로딩 중... (첫 실행 시 모델 다운로드 ~1.5GB)")
    from marker.converters.pdf import PdfConverter
    from marker.models import create_model_dict

    t0 = time.perf_counter()
    artifact_dict = create_model_dict()
    converter = PdfConverter(artifact_dict=artifact_dict)
    rendered = converter(str(PDF_PATH))
    elapsed = time.perf_counter() - t0

    md = rendered.markdown
    return md, 0.0, elapsed


# ---------------------------------------------------------------------------
# Stage 2 품질 평가 (선택적)
# ---------------------------------------------------------------------------

async def evaluate_with_stage2(md: str, doc_id: str) -> float:
    sys.path.insert(0, str(Path(__file__).parent))
    os.environ.setdefault("USE_MOCK_LLM", "false")
    from app.pipeline.stage2_validate_agent import _evaluate_quality
    score, issues, hitl, _ = await _evaluate_quality(md, doc_id, threshold=0.0)
    return score, issues


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------

async def main(skip_stage2: bool) -> None:
    print("=" * 60)
    print("PDF 파서 비교: pdf_03_complex.pdf")
    print("=" * 60)

    results = {}

    # -- PyMuPDF --
    print("\n[1/2] PyMuPDF 파싱...")
    try:
        md_pymupdf, img_ratio, t_pymupdf = parse_with_pymupdf()
        (OUT_DIR / "pymupdf_output.md").write_text(md_pymupdf, encoding="utf-8")
        metrics_pymupdf = measure_structure(md_pymupdf)
        metrics_pymupdf["parse_time_sec"] = round(t_pymupdf, 2)
        metrics_pymupdf["image_ratio"]    = round(img_ratio, 3)
        print(f"  완료: {t_pymupdf:.2f}s | {len(md_pymupdf):,} chars")
        results["pymupdf"] = {"metrics": metrics_pymupdf, "md": md_pymupdf}
    except Exception as e:
        print(f"  실패: {e}")
        results["pymupdf"] = {"error": str(e)}

    # -- Marker --
    print("\n[2/2] Marker 파싱...")
    try:
        md_marker, _, t_marker = parse_with_marker()
        (OUT_DIR / "marker_output.md").write_text(md_marker, encoding="utf-8")
        metrics_marker = measure_structure(md_marker)
        metrics_marker["parse_time_sec"] = round(t_marker, 2)
        metrics_marker["image_ratio"]    = 0.0
        print(f"  완료: {t_marker:.2f}s | {len(md_marker):,} chars")
        results["marker"] = {"metrics": metrics_marker, "md": md_marker}
    except Exception as e:
        print(f"  실패: {e}")
        results["marker"] = {"error": str(e)}

    # -- Stage 2 평가 --
    if not skip_stage2:
        print("\n[Stage 2] Gemini 품질 평가...")
        for name in ("pymupdf", "marker"):
            if "md" not in results.get(name, {}):
                continue
            try:
                score, issues = await evaluate_with_stage2(
                    results[name]["md"], f"compare_{name}"
                )
                results[name]["stage2_score"]  = round(score, 3)
                results[name]["stage2_issues"] = issues
                results[name]["metrics"]["stage2_score"] = round(score, 3)
                print(f"  {name}: score={score:.3f}, issues={len(issues)}개")
            except Exception as e:
                print(f"  {name} Stage 2 실패: {e}")
                results[name]["stage2_score"] = None

    # -- 비교 출력 --
    print("\n" + "=" * 60)
    print("비교 결과")
    print("=" * 60)

    labels = [
        ("chars",          "텍스트 크기 (chars)"),
        ("headings",       "제목 태그 수 (#/##/###)"),
        ("h1",             "  H1 (#)"),
        ("h2",             "  H2 (##)"),
        ("h3",             "  H3 (###)"),
        ("table_rows",     "표 행 수"),
        ("table_seps",     "표 개수 (근사)"),
        ("image_tags",     "이미지 태그"),
        ("parse_time_sec", "파싱 시간 (초)"),
        ("stage2_score",   "Stage2 품질 점수"),
    ]

    pm = results.get("pymupdf", {}).get("metrics", {})
    mk = results.get("marker",  {}).get("metrics", {})

    print(f"\n{'항목':<28} {'PyMuPDF':>12} {'Marker':>12}  판정")
    print("-" * 60)
    for key, label in labels:
        v_pm = pm.get(key, "N/A")
        v_mk = mk.get(key, "N/A")
        win = ""
        if key == "parse_time_sec":
            win = "◀ PyMuPDF 빠름" if isinstance(v_pm, float) and isinstance(v_mk, float) and v_pm < v_mk else ""
        elif key == "stage2_score":
            if isinstance(v_pm, float) and isinstance(v_mk, float):
                win = "◀ PyMuPDF" if v_pm > v_mk else ("◀ Marker ★" if v_mk > v_pm else "동점")
        elif key in ("chars", "headings", "table_rows", "table_seps"):
            if isinstance(v_pm, int) and isinstance(v_mk, int) and v_mk > v_pm:
                win = "◀ Marker ★"
        print(f"{label:<28} {str(v_pm):>12} {str(v_mk):>12}  {win}")

    # -- JSON 저장 --
    summary = {k: {kk: vv for kk, vv in v.items() if kk != "md"} for k, v in results.items()}
    (OUT_DIR / "comparison_result.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n결과 저장: {OUT_DIR}")
    print(f"  pymupdf_output.md  — PyMuPDF 변환 결과")
    print(f"  marker_output.md   — Marker 변환 결과")
    print(f"  comparison_result.json — 지표 비교")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-stage2", action="store_true", help="Stage 2 Gemini 평가 생략")
    args = parser.parse_args()
    asyncio.run(main(skip_stage2=args.skip_stage2))
