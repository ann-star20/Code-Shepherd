"""7단계 — Gemini 코멘트 생성 (RAG 인용 포함). 실행 후 삭제 예정.

test-performance-agent/showcase_issues.json(쇼케이스 1~6단계 산출)을 읽어
CombinedIssue로 만들고 llm_refiner.refine()으로 실제 Gemini 코멘트를 생성.
rag_context가 있으면 코멘트에 사내 가이드가 인용됨(R8).
"""
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def _load_key():
    for env in (HERE / ".env", ROOT / "test-performance-agent" / ".env"):
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith("GOOGLE_API_KEY="):
                    v = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if v:
                        os.environ["GOOGLE_API_KEY"] = v
                        return True
    return False


def main():
    has = _load_key()
    from contracts import CombinedIssue
    from llm_refiner import refine

    data = json.loads(
        (ROOT / "test-performance-agent" / "showcase_issues.json")
        .read_text(encoding="utf-8"))
    combined = [
        CombinedIssue(
            severity=i["severity"], file=i.get("file", ""), line=i.get("line"),
            message=i.get("message", ""), rule_id=i.get("rule_id", ""),
            suggestion=i.get("suggestion", ""), source_agent=i.get("_agent", ""),
            rag_context=i.get("rag_context", ""),
        ) for i in data
    ]
    crit = sum(1 for i in combined if i.severity == "Critical")
    major = sum(1 for i in combined if i.severity == "Major")
    verdict = "escalate" if crit >= 1 else ("rework" if major >= 3 else "lgtm")

    print("=" * 64)
    print("[7단계] Gemini 코멘트 생성 (RAG 인용 포함)")
    print("=" * 64)
    print("① 이슈 + 사내가이드(rag_context)를 Gemini에 줘서 리뷰 코멘트 생성")
    print(f"② 어디서: Gemini (구글) — 무료 키 (로드={has})")
    n_rag = sum(1 for i in combined if i.rag_context)
    print(f"   입력 이슈 {len(combined)}건 / rag_context 있는 이슈 {n_rag}건 / verdict={verdict}")
    comment = refine(combined, verdict, "junior")
    print("③ 실제 생성된 코멘트 (통째로):\n")
    print(comment)


if __name__ == "__main__":
    main()
