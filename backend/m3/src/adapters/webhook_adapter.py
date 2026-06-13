"""GitHub webhook adapter (Flask) — 메인 세션 소유.

- 기본 모드(D4, 웹훅 go 시): pull_request 이벤트 → diff/파일 조회 → src.graph.run_review()
  → comment_md 를 PR에 POST.
- `--probe` 모드(D1 90분 점검): 파이프라인 없이 [수신 → 서명검증 → diff 조회 → 코멘트 POST]
  체인만 증명하는 고정 코멘트를 단다.

재사용 원본: Code-Shepherd webhook-gateway 의 server.py(HMAC 검증·이벤트 필터·백그라운드
직렬 처리)와 gateway.fetch_pr_diff()(Accept: v3.diff) 패턴. registry·Postgres·
pr-comment-agent 경로는 v2 컷이라 가져오지 않는다.

실행: make webhook  (probe: .venv\\Scripts\\python -m src.adapters.webhook_adapter --probe)
공개: ngrok 터널을 WEBHOOK_PORT(기본 5000)로 연결.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import threading
import urllib.request
from datetime import datetime, timezone

from dotenv import load_dotenv
from flask import Flask, jsonify, request

load_dotenv()  # repo 루트 .env (키 값은 어디에도 출력 금지)

app = Flask(__name__)
WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
PORT = int(os.getenv("WEBHOOK_PORT", "5000"))
PROBE_MODE = "--probe" in sys.argv
API = "https://api.github.com"

# 한 번에 PR 1건 처리 (원본 패턴 유지 — LLM 호출 동시성/비용 제어)
_PROCESS_LOCK = threading.Lock()


def _verify_signature(payload: bytes, signature: str) -> bool:
    """GitHub X-Hub-Signature-256 검증. 시크릿 미설정 시 생략(로컬 데모 한정)."""
    if not WEBHOOK_SECRET:
        return True
    expected = "sha256=" + hmac.new(WEBHOOK_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def _gh(path: str, *, accept: str = "application/vnd.github+json",
        data: dict | None = None, method: str = "GET") -> str:
    req = urllib.request.Request(API + path, method=method)
    req.add_header("Accept", accept)
    req.add_header("Authorization", f"Bearer {GITHUB_TOKEN}")
    req.add_header("User-Agent", "dev3-review-agent")
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, body, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_pr_diff(full_name: str, pr_number: int) -> str:
    """PR unified diff 조회 — payload 에 diff 본문이 없어도 repo+번호로 조회 가능 (기준①)."""
    return _gh(f"/repos/{full_name}/pulls/{pr_number}", accept="application/vnd.github.v3.diff")


def fetch_pr_files(full_name: str, pr_number: int) -> list[str]:
    raw = _gh(f"/repos/{full_name}/pulls/{pr_number}/files?per_page=100")
    return [f["filename"] for f in json.loads(raw)]


def post_pr_comment(full_name: str, pr_number: int, body_md: str) -> int:
    raw = _gh(f"/repos/{full_name}/issues/{pr_number}/comments", data={"body": body_md}, method="POST")
    return json.loads(raw)["id"]


def _handle(full_name: str, pr_number: int, action: str, pr_author: str | None = None) -> None:
    with _PROCESS_LOCK:
        try:
            diff = fetch_pr_diff(full_name, pr_number)
            files = fetch_pr_files(full_name, pr_number)
            if PROBE_MODE:
                ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
                comment = (
                    "**[dev3-mvp webhook probe]** chain OK: received -> signature verified -> "
                    f"diff fetched -> comment posted\n\n"
                    f"- action: `{action}` / diff: {len(diff.splitlines())} lines / "
                    f"files: {len(files)} / at: {ts}"
                )
            else:
                from contracts import ReviewInput
                from src.graph import run_review
                from src.adapters.db_adapter import insert_review_issues

                out = run_review(ReviewInput(
                    diff=diff, file_paths=files,
                    repo_meta={"repo": full_name, "pr_number": pr_number, "source": "webhook"},
                ))
                comment = out.comment_md
                # ⑤ 뒤: violation findings → review_issue INSERT (ENABLE_DB_WRITE=true 시만)
                insert_review_issues(
                    out.findings or [],
                    pr_number=pr_number,
                    repository=full_name,
                    github_id=pr_author,
                    diff=diff,
                )
            cid = post_pr_comment(full_name, pr_number, comment)
            print(f"[webhook] PR #{pr_number} ({action}) comment_id={cid} "
                  f"mode={'probe' if PROBE_MODE else 'review'}", flush=True)
        except Exception as e:  # noqa: BLE001 — 서버 생존 우선, 원인은 로그로
            print(f"[webhook] PR #{pr_number} FAILED: {type(e).__name__}: {e}", flush=True)


@app.route("/webhook", methods=["POST"])
def webhook():
    if not _verify_signature(request.data, request.headers.get("X-Hub-Signature-256", "")):
        return jsonify({"error": "invalid signature"}), 401
    event = request.headers.get("X-GitHub-Event", "")
    data = request.get_json(silent=True) or {}
    if event == "pull_request" and data.get("action") in ("opened", "synchronize"):
        full_name = data["repository"]["full_name"]
        pr_number = data["pull_request"]["number"]
        pr_author = data["pull_request"].get("user", {}).get("login")
        print(f"[webhook] received pull_request.{data['action']} PR #{pr_number}", flush=True)
        threading.Thread(target=_handle, args=(full_name, pr_number, data["action"], pr_author), daemon=True).start()
        return jsonify({"status": "accepted", "pr": pr_number}), 202
    return jsonify({"status": "ignored", "event": event}), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "mode": "probe" if PROBE_MODE else "review"})


def main() -> None:
    print(f"[webhook] starting mode={'probe' if PROBE_MODE else 'review'} port={PORT}", flush=True)
    app.run(host="127.0.0.1", port=PORT)


if __name__ == "__main__":
    main()
