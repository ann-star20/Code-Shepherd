"""
run_case.py — 단일 eval 케이스로 Dev2 에이전트 실행

사용법:
    cd sub2_new
    python run_case.py                                         # mixed_case_01 기본값
    python run_case.py ../pj3_data/datasets/JH_PJ3/m2_mixed_case/mixed_case_02
"""
import sys
import asyncio

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import json
import pathlib
import uuid
from dotenv import load_dotenv

load_dotenv(pathlib.Path(__file__).parent / "dev2" / ".env")

from dev2.graph import run_dev2
from dev2.schema import Dev2State

DEFAULT_CASE = (
    pathlib.Path(__file__).parent.parent
    / "pj3_data/datasets/JH_PJ3/m2_mixed_case/mixed_case_01"
)


def _to_unified_diff(abs_path: str, content: str) -> str:
    """파일 전체를 신규 추가 unified diff 형식으로 변환. abs_path를 헤더에 사용해 도구가 실제 파일을 찾을 수 있게 한다."""
    lines = content.splitlines()
    header = f"--- /dev/null\n+++ b/{abs_path}\n@@ -0,0 +1,{len(lines)} @@\n"
    body = "\n".join(f"+{line}" for line in lines)
    return header + body


def load_case(case_dir: pathlib.Path) -> tuple[Dev2State, list[dict]]:
    py_file = case_dir / "vulnerable.py"
    code = py_file.read_text(encoding="utf-8")
    expected = json.loads((case_dir / "expected_issue.json").read_text(encoding="utf-8"))
    abs_path = str(py_file.resolve()).replace("\\", "/")
    diff = _to_unified_diff(abs_path, code)

    state: Dev2State = {
        "task_id":     str(uuid.uuid4()),
        "pr_id":       expected["case_id"],
        "pr_diff":     diff,
        "developer_id": "00000000-0000-0000-0000-000000000001",  # junior_dev_01 seed
        "skill_level": "junior",
        "tech_stack":  ["python"],
        "architecture_docs":   [],
        "coding_conventions":  "",
        "previous_pr_issues":  [],
    }
    return state, expected["expected_issues"]


async def main(case_dir: pathlib.Path) -> None:
    print(f"[eval] 케이스: {case_dir.name}")
    state, expected = load_case(case_dir)
    print(f"[eval] pr_id={state['pr_id']}  task_id={state['task_id']}")
    print(f"[eval] 기대 이슈 {len(expected)}개: {[e['id'] for e in expected]}\n")

    result = await run_dev2(state)

    print("=" * 60)
    print(f"[eval] 에이전트 출력 ({len(result)}개 AgentOutput)")
    for output in result:
        agent = output.get("agent", "?")
        issues = output.get("issues", [])
        summary = output.get("summary", {})
        print(f"\n  agent={agent}  issues={len(issues)}  summary={summary}")
        for i, issue in enumerate(issues, 1):
            print(f"    [{i}] {issue.get('severity'):8s}  rule={issue.get('rule_id'):10s}  "
                  f"line={issue.get('line'):4}  {issue.get('message', '')[:60]}")

    RULE_KEYWORD_MAP = {
        "SEC-001": ["B608", "sql", "injection"],
        "SEC-002": ["B602", "B603", "B605", "command", "injection"],
        "SEC-003": ["SEC-PT001", "path", "traversal", "directory"],
        "SEC-004": ["B602", "B603", "B605", "command", "injection", "os.system"],
        "SEC-005": ["B324", "B303", "md5", "hash"],
        "SEC-006": ["B105", "B106", "B107", "SEC-B105", "hardcod", "secret", "password", "token", "url"],
        "AUTH-001": ["SEC-AUTH001", "authorization", "missing authorization"],
    }

    detected_msgs = " ".join(
        (i.get("rule_id", "") + " " + i.get("message", "")).lower()
        for out in result for i in out.get("issues", [])
    )

    print("\n" + "=" * 60)
    print("[eval] 기대 이슈 vs 탐지 이슈 비교")
    for exp in expected:
        keywords = RULE_KEYWORD_MAP.get(exp["id"], [exp["id"].lower()])
        hit = any(kw.lower() in detected_msgs for kw in keywords)
        mark = "[OK]" if hit else "[--]"
        print(f"  {mark}  {exp['id']:10s}  {exp['severity']:8s}  {exp['title']}")


if __name__ == "__main__":
    case_path = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CASE
    asyncio.run(main(case_path))
