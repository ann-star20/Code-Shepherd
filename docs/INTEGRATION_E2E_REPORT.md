# Integration E2E Report — dev3 code_review_agent → Team m3

**Branch**: `feat/m3-dev3-integration`  
**Date**: 2026-06-13  
**Author**: kskt1234-netizen + Claude Sonnet 4.6

---

## 1. 통합 개요

dev3 팀의 `code_review_agent`(LangGraph 6노드 RAG 파이프라인)를 팀 스택의 `m3` 슬롯에 drop-in 교체했다.  
포트 8004, 계약 `M3ReviewRequest/Response`를 그대로 유지하며 팀 `docker-compose.yml` 무수정.

---

## 2. Task 3 — m3 단독 검증 결과

| 항목 | 결과 |
|------|------|
| `GET /health` | ✅ `{"status":"ok","adapter":"dev3"}` |
| Reindex (corpus 40청크, bge-m3 1024d) | ✅ ChromaDB 정상 |
| Smoke (scene1 diff → POST /review) | ✅ findings 2건, trace 6노드 |
| `make eval` (12/12 골든셋) | ✅ 12/12 pass |

---

## 3. Task 4 — 전체 스택 E2E 결과

### 3.1 인프라

- **실행 스택**: 구 Code-Shepherd 스택 (m0/m1/m2/m4/m5/api-core/frontend/neo4j)
- **우리 m3**: `code-shepherd-new-m3-1` (포트 8004)
- **네트워크 브리지**: `docker network connect --alias m3 code-shepherd_code-shepherd code-shepherd-new-m3-1`

### 3.2 파이프라인 체인 (trace_id: b08e860e-232c-4696-8ba2-f03b846e8620)

```
m1 /triggers/pr (HMAC 202)
  → m2 /analyze/static       200  45ms
  → m2 /analyze/security     200  61ms
  → m3 /verify/tests         200  94ms  ← stub (빈 pass)
  → m3 /analyze/performance  200  97ms  ← stub (빈 pass)
  → m3 /review               200 4094ms ← dev3 RAG 파이프라인
verdict: rework | comment_posted: true
```

### 3.3 RAG 파이프라인 trace (⓪→⑤)

| 노드 | 결과 |
|------|------|
| ⓪ assemble_input | pr_context 1211자 |
| ① extract_concepts | 개념 5개, 지시 8개 |
| ② retrieve (KMS) | 청크 8개 (CONV-API-001, CONV-DB-004, CONV-ERR-006, CONV-SQL-008) |
| ③ check_sufficiency | route=proceed |
| ④ judge | findings 2건 (violation 2) |
| ⑤ compose_comment | 코멘트 1269자 |

### 3.4 findings (CONV-DB-004, CONV-SQL-008)

| rule_id | severity | file | 근거 |
|---------|----------|------|------|
| CONV-DB-004 | Major | src/payment.py | N+1 쿼리 — 루프 내 DB 호출 |
| CONV-SQL-008 | Major | src/payment.py | f-string SQL 조립 위험 |

### 3.5 GitHub PR 코멘트

- PR: `kskt1234-netizen/-dev3-demo#4`
- 코멘트 URL: `https://github.com/kskt1234-netizen/-dev3-demo/pull/4#issuecomment-4641726188`
- 상태: ✅ 게시 완료

### 3.6 DB 적재 (Cloud SQL — `review_issue` 테이블)

| keyword | sub_category | severity | code_snippet | name_of_function |
|---------|-------------|----------|--------------|------------------|
| 동기 HTTP 호출 | Async Sync HTTP Call - Event Loop Blocking | medium | requests.get(...) | verify_payment |
| 동기 HTTP 호출 | Async Sync HTTP Call - Event Loop Blocking | medium | requests.post(...) | refund |
| N+1 쿼리 | N+1 Query - Database Loop Call | medium | for oid in order_ids: ... | — |
| SQL 인젝션 위험 | SQL Injection Risk - Unsafe Query Construction | medium | db.query(f"...") | — |

`ENABLE_DB_WRITE=false` 복귀 확인 ✅

---

## 4. 발견 이슈 및 해결 내역

| 이슈 | 원인 | 해결 |
|------|------|------|
| Dockerfile COPY 경로 오류 | context=`./backend`인데 dev3 경로 그대로 사용 | 모든 COPY 앞에 `m3/` prefix 추가 |
| 볼륨 마운트 `.venv` 덮어쓰기 | `./backend/m3:/app/service`가 빌드된 `.venv` 삭제 | override 볼륨: `.chroma`/`.cache`/`corpus`만 추가 마운트 |
| HMAC 시크릿 불일치 | 우리 `.env`(49자)와 m1 컨테이너(64자)가 다른 시크릿 | m1 내 `_send_test_webhook.py` 활용 (올바른 시크릿 하드코딩됨) |
| m1→m3 네트워크 미연결 | Docker 네트워크가 서로 다른 스택 | `docker network connect --alias m3 code-shepherd_code-shepherd code-shepherd-new-m3-1` |
| `/verify/tests`, `/analyze/performance` 404 | dev3 m3에 해당 엔드포인트 없음 | 팀 계약 호환 스텁 엔드포인트 추가 |
| `insert_review_issues` 인자 순서 오류 | `(findings, owner, repo, pr_number)` → 잘못된 타입 | `(findings, pr_number, repository)` 로 수정 |

---

## 5. 잔여 리스크

| 항목 | 내용 | 우선순위 |
|------|------|---------|
| 네트워크 재연결 필요 | `docker compose down m3` 시 네트워크 재생성 → 매번 `docker network connect` 필요 | 중 |
| api-core ingest 미연동 | 데모 레포 미등록 → m1 `pr_trigger_skipped` 로그 없이 진행됨 (실제 flow에선 등록 필요) | 저 |
| 프론트 렌더 미확인 | `GET /review` API 응답은 검증됐으나 UI 렌더링은 브라우저 직접 확인 필요 | 저 |
| eval 캐시 의존 | 현재 eval 12/12는 캐시 hit 기반 — 캐시 초기화 후 재실행 시 LLM 비용 발생 | 정보 |

---

## 6. 최종 커밋 목록

| 커밋 | 내용 |
|------|------|
| 38580575 | docs: 보정 3건 + 보수 운영 프로토콜 추가 |
| 845065a5 | feat(m3): dev3 code_review_agent 이식 (Task 2) |
| 14fc6c77 | feat(m3): /verify/tests, /analyze/performance 스텁 추가 |
| e25787de | feat(m3): /review 엔드포인트에 insert_review_issues 연결 |
