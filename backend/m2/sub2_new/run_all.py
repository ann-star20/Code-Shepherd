"""
run_all.py — 전체 m2_mixed_case 배치 테스트 + 파이프라인 2 테스트

사용법:
    cd sub2_new
    python run_all.py > result_all.txt 2>&1
"""
import asyncio
import json
import pathlib
import uuid
from dotenv import load_dotenv

load_dotenv(pathlib.Path(__file__).parent / "dev2" / ".env")

from dev2.graph import run_dev2
from dev2.aggregate_graph import run_aggregate
from dev2.schema import Dev2State

CASES_ROOT = (
    pathlib.Path(__file__).parent.parent
    / "pj3_data/datasets/JH_PJ3/m2_mixed_case"
)

DEVELOPER_ID = "00000000-0000-0000-0000-000000000001"  # junior_dev_01

RULE_KEYWORD_MAP = {
    "SEC-001": ["B608", "sql", "injection"],
    "SEC-002": ["B602", "B603", "B605", "command", "injection"],
    "SEC-003": ["SEC-PT001", "path", "traversal", "directory"],
    "SEC-004": ["B602", "B603", "B605", "command", "injection", "os.system"],
    "SEC-005": ["B324", "B303", "md5", "hash"],
    "SEC-006": ["B105", "B106", "B107", "SEC-B105", "hardcod", "secret", "password", "token", "url"],
    "AUTH-001": ["SEC-AUTH001", "authorization", "missing authorization"],
}


def _to_unified_diff(abs_path: str, content: str) -> str:
    lines = content.splitlines()
    header = f"--- /dev/null\n+++ b/{abs_path}\n@@ -0,0 +1,{len(lines)} @@\n"
    body = "\n".join(f"+{line}" for line in lines)
    return header + body


def load_case(case_dir: pathlib.Path):
    py_file = case_dir / "vulnerable.py"
    json_file = case_dir / "expected_issue.json"
    if not py_file.exists() or not json_file.exists():
        return None, None
    code = py_file.read_text(encoding="utf-8")
    expected = json.loads(json_file.read_text(encoding="utf-8"))
    abs_path = str(py_file.resolve()).replace("\\", "/")
    state: Dev2State = {
        "task_id":            str(uuid.uuid4()),
        "pr_id":              expected["case_id"],
        "pr_diff":            _to_unified_diff(abs_path, code),
        "developer_id":       DEVELOPER_ID,
        "skill_level":        "junior",
        "tech_stack":         ["python"],
        "architecture_docs":  [],
        "coding_conventions": "",
        "previous_pr_issues": [],
    }
    return state, expected.get("expected_issues", [])


def check_hits(result: list[dict], expected: list[dict]) -> tuple[int, int]:
    detected_msgs = " ".join(
        (i.get("rule_id", "") + " " + i.get("message", "")).lower()
        for out in result for i in out.get("issues", [])
    )
    hit = 0
    for exp in expected:
        keywords = RULE_KEYWORD_MAP.get(exp["id"], [exp["id"].lower()])
        if any(kw.lower() in detected_msgs for kw in keywords):
            hit += 1
    return hit, len(expected)


# ── 파이프라인 1: 단일 케이스 실행 ──────────────────────────────────────────────

async def run_case(case_dir: pathlib.Path) -> dict:
    state, expected = load_case(case_dir)
    if state is None:
        return {"case": case_dir.name, "skip": True}

    print(f"\n[P1] {case_dir.name} (pr_id={state['pr_id']})")
    try:
        result = await run_dev2(state)
    except Exception as e:
        print(f"  ERROR: {e}")
        return {"case": case_dir.name, "error": str(e), "result": [], "expected": expected}

    hit, total = check_hits(result, expected)
    issues_flat = [i for out in result for i in out.get("issues", [])]
    print(f"  탐지 {len(issues_flat)}개 | 기대 {total}개 중 {hit}개 매칭")
    for out in result:
        for i in out.get("issues", []):
            print(f"    {i.get('severity'):8s}  {i.get('rule_id'):12s}  line={i.get('line'):4}  {i.get('message','')[:55]}")

    return {
        "case": case_dir.name,
        "result": result,
        "expected": expected,
        "hit": hit,
        "total": total,
        "task_id": state["task_id"],
        "pr_id": state["pr_id"],
    }


# ── 파이프라인 2: aggregate → comment_refine → github_comment → slack ──────────

async def run_pipeline2(case_result: dict) -> None:
    print("\n" + "=" * 60)
    print(f"[P2] 파이프라인 2 테스트 (케이스: {case_result['case']})")

    payload = {
        "task_id":  case_result["task_id"],
        "pr_id":    case_result["pr_id"],
        "developer": {
            "id":          DEVELOPER_ID,
            "skill_level": "junior",
            "tech_stack":  ["python"],
        },
        "context": {
            "architecture_docs":  [],
            "coding_conventions": "",
            "previous_pr_issues": [],
        },
        "all_results": case_result["result"],
    }

    try:
        state = await run_aggregate(payload)
        print(f"  aggregate:      이슈 {len(state.get('aggregated_issues', []))}개 취합")
        print(f"  total_summary:  {state.get('total_summary', {})}")
        cb = state.get("comment_body", "")
        print(f"  comment_body:   {cb[:120]}{'...' if len(cb) > 120 else ''}")
        print(f"  github_comment_url: {state.get('github_comment_url', '(미등록 — GITHUB_TOKEN 없음)')}")
    except Exception as e:
        print(f"  ERROR: {e}")


# ── 메인 ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    cases = sorted(CASES_ROOT.iterdir())
    print(f"총 {len(cases)}개 케이스 발견\n" + "=" * 60)

    # 파이프라인 1: 전체 케이스 순차 실행
    results = []
    for case_dir in cases:
        if case_dir.is_dir():
            r = await run_case(case_dir)
            results.append(r)

    # 요약 테이블
    print("\n" + "=" * 60)
    print("[요약] 파이프라인 1 결과")
    print(f"  {'케이스':<35} {'탐지/기대':>8}  상태")
    print("-" * 60)
    total_hit = total_exp = 0
    p2_candidate = None
    for r in results:
        if r.get("skip"):
            print(f"  {r['case']:<35}  SKIP")
            continue
        if r.get("error"):
            print(f"  {r['case']:<35}  ERROR")
            continue
        hit, total = r.get("hit", 0), r.get("total", 0)
        total_hit += hit
        total_exp += total
        status = "OK" if hit == total else f"MISS {total-hit}"
        print(f"  {r['case']:<35} {hit}/{total:>3}     {status}")
        if p2_candidate is None and r.get("result"):
            p2_candidate = r  # 파이프라인 2 테스트에 첫 번째 성공 케이스 사용

    print("-" * 60)
    print(f"  전체 탐지율: {total_hit}/{total_exp}")

    # 파이프라인 2 테스트
    if p2_candidate:
        await run_pipeline2(p2_candidate)
    else:
        print("\n[P2] 파이프라인 2 테스트 건너뜀 — 파이프라인 1 결과 없음")


if __name__ == "__main__":
    asyncio.run(main())
