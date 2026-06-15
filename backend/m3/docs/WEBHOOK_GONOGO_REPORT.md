# 웹훅 90분 점검 — 최종 go/no-go 보고서

작성: 2026-06-12 10:05 KST  
점검 범위: 브리프 §2.5 통과 기준 3종

---

## 체크리스트 집계

| 기준 | 결과 | 근거 |
|---|---|---|
| ① payload에 diff(또는 diff 조회 가능한 정보) 포함 | **PASS** | `GET /repos/{full_name}/pulls/{n}` Accept: v3.diff → 정상 diff 수신. `webhook_adapter.fetch_pr_diff()` 검증 완료. |
| ② PAT로 PR 코멘트 POST 성공 | **PASS** | `POST /issues/{n}/comments` → 201, comment_id 반환 확인. probe 모드 E2E 완주, 실제 PR에 코멘트 등록됨. |
| ③ ngrok 터널 30분 유지 | **PASS** | 터널 `dev3-webhook` → localhost:5000 기동 01:43:48 KST. 현재 10:04:48 KST 기준 **8시간 21분 유지** (요구 30분 초과). ngrok agent API 확인: 7 connections, proto=https, addr=http://localhost:5000. |

---

## 구현 상태

- `src/adapters/webhook_adapter.py`: HMAC-SHA256 서명검증, diff 조회, 파일목록 조회, 코멘트 POST, --probe 모드 모두 구현 완료. 커밋 `f745ae0` 포함.
- 공개 URL: `https://phonics-underwent-scrounger.ngrok-free.dev` (무료 플랜 — URL은 재기동마다 바뀜, 데모 직전 재등록 필요)
- 주의: 동일 URL에 port 8001 터널(m1-orchestrator)도 공존. 무료 플랜의 단일 도메인 공유 특성. D4 데모 시 port 8001 터널 제거 후 단독 운영 권장.

---

## 권고: **GO**

3종 기준 전부 PASS. D4(웹훅 통합)에서 `src.graph.run_review()` 1줄 교체로 전체 파이프라인 연결 가능.

D4 연결 범위 (사전 합의):
- `webhook_adapter.py` 골조 그대로 유지
- `if not PROBE_MODE:` 블록에 `run_review()` 호출 삽입 (이미 스텁 코드 존재)
- registry/DB/pr-comment-agent 코드는 V2 컷 유지

---

## 다음 단계 (D2 메인 세션)

1. `src/llm.py` — Anthropic 클라이언트 + 디스크 캐시 + 프롬프트 캐싱
2. `src/nodes/extract_concepts.py` — ① 노드 (LLM → Concept 목록 + 쿼리 문자열)
3. `src/nodes/retrieve.py` — ② 노드 (Chroma top-k 검색)
4. `src/nodes/check_sufficiency.py` — ③ 노드 (Command routing: proceed/requery/gap_report)
5. `src/nodes/judge.py` — ④ 노드 (Finding 목록 생성)
6. `src/nodes/compose_comment.py` — ⑤ 노드 (markdown 코멘트 + GapReport)
7. `src/graph.py` — LangGraph 조립 + `run_review()` 진입점
