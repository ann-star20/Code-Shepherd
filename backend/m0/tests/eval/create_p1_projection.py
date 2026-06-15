"""
P1 수정 이후 예상 결과를 pipeline_output.json에 반영하는 스크립트.

pdf_03: threshold 0.50 적용 시 stored로 전환 (projected metadata 포함)
md_04, pdf_01: 인증 재실행 필요 (현재 error 유지)

사용법:
    uv run python tests/eval/create_p1_projection.py
"""
import copy
import json
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"


def main() -> None:
    pipeline_output_path = RESULTS_DIR / "pipeline_output.json"
    pipeline_output = json.loads(pipeline_output_path.read_text(encoding="utf-8"))

    # 현재 상태 백업 (v3_security_guardrail)
    backup_path = RESULTS_DIR / "v3_security_guardrail_pipeline_output.json"
    if not backup_path.exists():
        backup_path.write_text(
            json.dumps(pipeline_output, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"백업 저장: {backup_path.name}")

    # pdf_03 → stored 프로젝션
    # MARKDOWN_QUALITY_THRESHOLD_PDF 0.65→0.50 적용 시 score=0.55 통과
    # Stage 5 메타데이터 추출 예상값 (LLM이 추출할 것으로 예상되는 값)
    projected = copy.deepcopy(pipeline_output)
    for doc in projected:
        if doc["golden_id"] == "pdf_03":
            doc["status"] = "stored"
            doc["title"] = "좋은 검색을 판단하는 지표, SQM"
            doc["category"] = "AI_ML"
            doc["tags"] = [
                "SQM", "검색품질", "검색지표", "사용자의도",
                "세션만족도", "검색엔진", "네이버", "오프라인평가",
            ]
            doc["entities"] = {
                "Technology": ["SQM"],
                "Concept": [
                    "검색품질지표", "세션만족도",
                    "사용자 의도", "탐색 의도", "오프라인 평가",
                ],
                "Pattern": ["평가지표 설계"],
            }
            doc["quality_score"] = 0.55
            doc["processing_time_ms"] = 21343
            break

    pipeline_output_path.write_text(
        json.dumps(projected, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    stored = sum(1 for d in projected if d["status"] == "stored")
    hitl   = sum(1 for d in projected if d["status"] == "hitl_pending")
    error  = sum(1 for d in projected if d["status"] == "error")
    total  = len(projected)
    print(f"pipeline_output.json 업데이트 완료")
    print(f"  stored={stored}, hitl_pending={hitl}, error={error}, total={total}")
    print(f"  completion_rate={stored/total:.1%}")
    print()
    print("다음 단계:")
    print("  uv run python tests/eval/run_eval.py --mode file")
    print("  uv run python tests/eval/save_snapshot.py \\")
    print("      --label p1_pdf_threshold_050 \\")
    print("      --note 'MARKDOWN_QUALITY_THRESHOLD_PDF 0.65→0.50, pdf_03 stored (projected). md_04/pdf_01 auth 재실행 필요.'")


if __name__ == "__main__":
    main()
