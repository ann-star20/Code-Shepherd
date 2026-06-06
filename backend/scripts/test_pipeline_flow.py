#!/usr/bin/env python3
"""파이프라인 전체 흐름 자동 테스트 스크립트.

Usage:
  python scripts/test_pipeline_flow.py
  python scripts/test_pipeline_flow.py --url "https://owasp.org/www-project-top-ten/"
  python scripts/test_pipeline_flow.py --base-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys
import time
from pathlib import Path

import httpx

DEFAULT_URL = "https://docs.djangoproject.com/en/6.0/topics/security/"
BASE = "http://localhost:8000"
POLL_INTERVAL = 2   # seconds


class _Tee:
    """stdout을 터미널과 파일에 동시에 쓴다."""
    def __init__(self, file):
        self._terminal = sys.__stdout__
        self._file = file

    def write(self, data: str) -> None:
        self._terminal.write(data)
        self._file.write(data)

    def flush(self) -> None:
        self._terminal.flush()
        self._file.flush()
POLL_TIMEOUT  = 6  # seconds


def ok(label: str, data: dict) -> None:
    print(f"\n✔  {label}")
    for k, v in data.items():
        print(f"   {k}: {v}")


def fail(label: str, resp: httpx.Response) -> None:
    print(f"\n✘  {label}  [{resp.status_code}]")
    print(f"   {resp.text[:300]}")
    sys.exit(1)


def section(title: str) -> None:
    print(f"\n{'─'*55}\n  {title}\n{'─'*55}")


def step_register(client: httpx.Client, target_url: str) -> str:
    section("STEP 1 — URL 등록")
    resp = client.post("/api/documents", json={"urls": [target_url]})
    if resp.status_code not in (200, 201):
        fail("POST /api/documents", resp)
    doc = resp.json()["documents"][0]
    state = doc["state"]
    label = "등록 완료" if state == "PENDING" else f"기존 문서 재사용 (state={state})"
    ok(label, {"doc_id": doc["doc_id"], "state": state, "url": doc["original_url"]})
    if state == "FAILED":
        print("   ℹ  이전 실행이 실패한 문서입니다. 트리거 API가 재실행합니다.")
    elif state == "COMMITTED":
        print("   ℹ  이미 COMMITTED된 문서입니다. 트리거하려면 DB에서 state를 PENDING으로 리셋하세요.")
    return doc["doc_id"]


def step_prescan(client: httpx.Client, doc_id: str) -> None:
    section("STEP 2 — Pre-scan (메타 추론)")
    resp = client.post(f"/api/documents/{doc_id}/prescan")
    if resp.status_code != 200:
        fail(f"POST /api/documents/{doc_id}/prescan", resp)
    s = resp.json()
    ok("Pre-scan 결과", {
        "framework":  s.get("framework") or "(미확인)",
        "version":    s.get("version") or "(미확인)",
        "lang":       s.get("lang") or "(미확인)",
        "confidence": s.get("infer_confidence"),
        "status":     s.get("infer_status"),
    })
    if s.get("infer_status") == "manual_required":
        suggestions = s.get("suggested_frameworks", [])
        print(f"   ⚠  신뢰도 낮음 — 제안 프레임워크: {suggestions[:5]}")


def step_trigger(client: httpx.Client, doc_id: str) -> str:
    section("STEP 3 — 파이프라인 트리거")
    resp = client.post("/api/pipeline/trigger", json={"doc_id": doc_id})
    if resp.status_code != 202:
        fail("POST /api/pipeline/trigger", resp)
    t = resp.json()
    ok("트리거 완료", {"session_id": t["session_id"], "message": t["message"]})
    return t["session_id"]


def step_poll_logs(client: httpx.Client, session_id: str) -> str:
    section("STEP 4 — 파이프라인 로그 폴링")
    terminal_states = {"COMMITTED", "FAILED"}
    deadline = time.time() + POLL_TIMEOUT
    last_count = 0
    state = "…"
    hitl_triggered = False

    while time.time() < deadline:
        resp = client.get(f"/api/pipeline/logs/{session_id}")
        if resp.status_code != 200:
            fail("GET /api/pipeline/logs", resp)

        data  = resp.json()
        logs  = data.get("logs", [])
        state = data.get("doc_state") or "…"

        for entry in logs[last_count:]:
            print(f"   [{entry['agent']:10s}] {entry['level']:5s}  {entry['message']}")
        last_count = len(logs)

        print(f"   ── doc_state: {state}")
        if state in terminal_states:
            return state

        # HITL 게이트: EXTRACTED 상태면 자동 승인 → 커밋 트리거
        if state == "EXTRACTED" and not hitl_triggered:
            hitl_triggered = True
            print("   ── HITL 게이트 감지 — 자동 승인 + 커밋 트리거")
            client.post(f"/api/staging/{session_id}/approve")
            client.post(f"/api/staging/{session_id}/commit")
            deadline = time.time() + 30  # Celery write→resolve 체인 완료 대기

        time.sleep(POLL_INTERVAL)

    print(f"\n⚠  {POLL_TIMEOUT}초 초과 — 마지막 상태: {state}")
    return state


def step_staging(client: httpx.Client, session_id: str) -> None:
    section("STEP 5 — Staging 조회")
    resp = client.get(f"/api/staging/{session_id}")
    if resp.status_code != 200:
        fail(f"GET /api/staging/{session_id}", resp)
    body = resp.json()
    concepts = body if isinstance(body, list) else body.get("concepts", [])
    print(f"   총 {len(concepts)}개 컨셉")
    for c in concepts[:5]:
        print(
            f"   · {(c.get('concept_name') or '?'):<30s}"
            f"  state={c.get('state','?')}"
            f"  severity={c.get('severity','?')}"
            f"  domains={c.get('domains',[])}"
        )
    if len(concepts) > 5:
        print(f"   ... 외 {len(concepts) - 5}개")


def step_diff(client: httpx.Client, session_id: str) -> None:
    section("STEP 6 — Diff 확인")
    resp = client.get(f"/api/staging/{session_id}/diff")
    if resp.status_code != 200:
        fail(f"GET /api/staging/{session_id}/diff", resp)
    diff = resp.json()
    added   = diff.get("added",   [])
    changed = diff.get("changed", [])
    removed = diff.get("removed", [])
    print(f"   추가: {len(added)}  변경: {len(changed)}  제거: {len(removed)}")
    for item in added[:3]:
        print(f"   + {item.get('concept_name') or item}")
    for item in changed[:3]:
        print(f"   ~ {item.get('concept_name') or item}")


def main() -> None:
    parser = argparse.ArgumentParser(description="파이프라인 E2E 테스트")
    parser.add_argument("--url",      default=DEFAULT_URL, help="수집할 문서 URL")
    parser.add_argument("--base-url", default=BASE,        help="백엔드 주소")
    args = parser.parse_args()

    log_dir = Path(__file__).parent.parent / "logs"
    os.makedirs(log_dir, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = log_dir / f"{ts}.log"
    log_file = open(log_path, "w", encoding="utf-8")  # noqa: SIM115
    sys.stdout = _Tee(log_file)

    print("\n🚀  Pipeline E2E Test")
    print(f"    target : {args.url}")
    print(f"    backend: {args.base_url}")
    print(f"    log    : {log_path}")

    with httpx.Client(base_url=args.base_url, timeout=15.0) as client:
        doc_id      = step_register(client, args.url)
        step_prescan(client, doc_id)
        session_id  = step_trigger(client, doc_id)
        final_state = step_poll_logs(client, session_id)

        if final_state == "COMMITTED":
            step_staging(client, session_id)
            step_diff(client, session_id)
            print("\n✅  전체 파이프라인 완료 — COMMITTED")
        else:
            print(f"\n❌  파이프라인 종료 상태: {final_state}")

    sys.stdout = sys.__stdout__
    log_file.close()
    print(f"📄  로그 저장: {log_path}")

    if final_state != "COMMITTED":
        sys.exit(1)


if __name__ == "__main__":
    main()
