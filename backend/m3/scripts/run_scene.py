"""시연 장면 단건 실행 — Streamlit 장애 시 터미널 백업 경로.

사용: python scripts/run_scene.py fixtures/demo/scene4_hotswap.txt
스왑 중 eval 금지 — 이 스크립트는 골든셋을 건드리지 않는 단건 실행이다.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from contracts import ReviewInput
from src.graph import run_review_traced


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python scripts/run_scene.py <diff-file>")
        sys.exit(1)
    diff = Path(sys.argv[1]).read_text(encoding="utf-8")
    out, trace = run_review_traced(ReviewInput(diff=diff, file_paths=[], repo_meta={}))

    print("=== 실행 흐름 ===")
    for r in trace:
        mark = "OK " if r["ok"] else "FAIL"
        print(f"{mark} {r['label']} | {r['summary']} | {r['ms']}ms")

    print("\n=== 판정 ===")
    if out.gap_report:
        print("지침공백 (gap) — 신규 지침 제안 포함")
    elif not out.findings:
        print("지적 없음 (정상)")
    for f in out.findings:
        print(f"[{f.rule_id}] {f.verdict} ({f.severity})")
        for line in f.evidence_lines[:2]:
            print(f"  evidence: {line.strip()[:80]}")

    print("\n=== 코멘트 (앞 600자) ===")
    print(out.comment_md[:600])


if __name__ == "__main__":
    main()
