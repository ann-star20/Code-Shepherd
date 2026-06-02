"""GitHub Webhook 수신 서버 (공용 게이트웨이).

신입이 PR을 올리면 GitHub가 이 서버로 신호(POST)를 쏜다.
서버는 PR 정보를 추출해 등록된 분석 에이전트들을 호출하고 코멘트를 등록한다.

실행:
    py server.py                 # http://localhost:5000 에서 대기
그리고 ngrok 으로 공개:
    ngrok http 5000              # → https://xxxx.ngrok.io 주소를 GitHub Webhook에 등록

GitHub 설정:
    레포 Settings → Webhooks → Add webhook
      - Payload URL: https://xxxx.ngrok.io/webhook
      - Content type: application/json
      - Events: "Pull requests" 선택
"""
from __future__ import annotations

import hashlib
import hmac
import os
import sys
import threading

from flask import Flask, request, jsonify

# .env 로드
_envp = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_envp):
    for line in open(_envp, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from registry import PRContext                       # noqa: E402
from gateway import process_pr                        # noqa: E402
import agents.dev3_adapter  # noqa: E402,F401  (등록 트리거 — import만으로 register됨)
import agents.dev2_adapter  # noqa: E402,F401  (Dev2 정적분석·보안 — import만으로 register됨)

app = Flask(__name__)
WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")


def _verify_signature(payload: bytes, signature: str) -> bool:
    """GitHub Webhook 서명 검증 (시크릿 설정 시)."""
    if not WEBHOOK_SECRET:
        return True  # 시크릿 미설정 시 검증 생략 (데모)
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature or "")


@app.route("/webhook", methods=["POST"])
def webhook():
    if not _verify_signature(request.data, request.headers.get("X-Hub-Signature-256", "")):
        return jsonify({"error": "invalid signature"}), 401

    event = request.headers.get("X-GitHub-Event", "")
    data = request.get_json(silent=True) or {}

    # PR이 열리거나(opened) 새 커밋 push(synchronize) 됐을 때만 처리
    if event == "pull_request" and data.get("action") in ("opened", "synchronize", "reopened"):
        pr = data["pull_request"]
        ctx = PRContext(
            repo_full_name=data["repository"]["full_name"],
            clone_url=data["repository"]["clone_url"],
            pr_number=data["number"],
            commit_sha=pr["head"]["sha"],
            branch=pr["head"]["ref"],
            author=pr["user"]["login"],
        )
        print(f"\n🔔 PR #{ctx.pr_number} 수신 ({ctx.repo_full_name}, by {ctx.author})")
        # 분석은 백그라운드로 (GitHub에 빠르게 200 응답)
        threading.Thread(target=_process_safe, args=(ctx,), daemon=True).start()
        return jsonify({"status": "accepted", "pr": ctx.pr_number}), 202

    return jsonify({"status": "ignored", "event": event}), 200


def _process_safe(ctx: PRContext):
    try:
        out = process_pr(ctx, do_comment=True)
        print(f"✅ PR #{ctx.pr_number} 처리 완료 — {out.get('issue_count')} 이슈, "
              f"verdict={out.get('verdict')}, post={out.get('post', {}).get('mode')}")
    except Exception as e:  # noqa: BLE001
        print(f"❌ PR #{ctx.pr_number} 처리 실패: {e}")


@app.route("/health", methods=["GET"])
def health():
    from registry import registered_agents
    return jsonify({
        "status": "ok",
        "registered_agents": [a.name for a in registered_agents()],
    })


if __name__ == "__main__":
    from registry import registered_agents
    print("=" * 60)
    print("  Webhook Gateway 시작")
    print("=" * 60)
    print(f"  등록된 분석 에이전트: {[a.name for a in registered_agents()]}")
    print("  Webhook URL: http://localhost:5000/webhook")
    print("  ngrok http 5000  으로 공개 주소를 만드세요.")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000)
