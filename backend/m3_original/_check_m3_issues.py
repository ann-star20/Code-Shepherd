"""m3 실분석 이슈 비어있지 않은지 확정 — m1 이 보내는 모양 그대로 직접 호출.

/verify/tests + /analyze/performance 에 PR#4 페이로드(clone_url/commit_sha/diff 본문)를 POST 해
IssueItem 건수와 내용을 출력한다. (읽기 전용 — 분석만)
"""
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

M3 = "http://127.0.0.1:8004"
DIFF_URL = "https://github.com/kskt1234-netizen/-dev3-demo/pull/4.diff"


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "shepherd-check"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def _post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"{M3}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode())


diff_text = _get(DIFF_URL)
assert diff_text.startswith("diff --git"), "diff 본문이 아님!"

payload = {
    "task_id": "shepherd-verify-pr4",
    "pr_id": "4",
    "pr_diff": diff_text,
    "clone_url": "https://github.com/kskt1234-netizen/-dev3-demo.git",
    "commit_sha": "27f5c96142260206ce714da1294aefbbddb0f4f6",
    "developer": {"id": "kskt1234-netizen"},
}

for path in ("/verify/tests", "/analyze/performance"):
    data = _post(path, payload)
    issues = data.get("issues", [])
    print(f"\n===== {path}  agent={data.get('agent')}  issues={len(issues)} "
          f"summary={data.get('summary')}  ms={data.get('execution_ms')} =====")
    for it in issues:
        print(f"  [{it['severity']}] {it.get('rule_id')} "
              f"{it.get('file')}:{it.get('line')} — {it.get('message')}")
