"""로컬 HMAC 프리플라이트 — 데모 PR#4 페이로드를 서명해 m1 /triggers/pr 로 전송.

용도: m1 의 github_webhook_secret 가 맞는지(=401 아님) + ingest 경로가 도는지 확인.
팀 미등록 상태에서는 200 skipped 가 정상(서명은 통과, ingest 가 404 skip).
사용자가 웹사이트에서 레포 등록 후 다시 돌리면 dispatched 로 흐른다.
"""
import hashlib
import hmac
import json
import os
import urllib.error
import urllib.request

SECRET = os.environ.get(
    "GITHUB_WEBHOOK_SECRET",
    "d179fe30e4e4550c7452a94b2b6ebfd2bc7b50eb1ba63815fe114bc31317d840",
)
M1_URL = os.environ.get("M1_URL", "http://127.0.0.1:8001")
AUTHOR = os.environ.get("PR_AUTHOR", "kskt1234-netizen")

payload = {
    "action": "opened",
    "number": 4,
    "repository": {
        "full_name": "kskt1234-netizen/-dev3-demo",
        "clone_url": "https://github.com/kskt1234-netizen/-dev3-demo.git",
    },
    "pull_request": {
        "number": 4,
        "user": {"login": AUTHOR},
        "diff_url": "https://github.com/kskt1234-netizen/-dev3-demo/pull/4.diff",
        "head": {
            "sha": "27f5c96142260206ce714da1294aefbbddb0f4f6",
            "repo": {"clone_url": "https://github.com/kskt1234-netizen/-dev3-demo.git"},
        },
    },
    "sender": {"login": AUTHOR},
}

body = json.dumps(payload).encode()
sig = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
req = urllib.request.Request(
    f"{M1_URL}/triggers/pr",
    data=body,
    headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=120) as r:
        print("HTTP", r.status)
        print(r.read().decode())
except urllib.error.HTTPError as e:
    print("HTTP", e.code)
    print(e.read().decode())
