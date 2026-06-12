# 시연 스크립트 — 4장면 (D5 리허설 완료 기준)

> 발표 순서 고정 (브리프 §7). 입력은 전부 `fixtures/demo/` 박제본.
> 사전 준비: `make reindex` (bge-m3 인덱스) + 리허설 1회로 LLM 캐시 워밍 → 시연 중 API 0원·결정적 재생.
> 실행 UI: 팀 스택 통합 환경 (프론트 http://localhost:5173). 장애 시 폴백: Streamlit `make demo`.
> **스왑 중 `make eval` 절대 금지** — 골든셋 지표 오염.

---

## 통합 환경 실행 절차 (2026-06-13 기준)

### 기동 순서

```bash
# 1. Ollama bge-m3 확인
ollama list  # bge-m3:latest 있어야 함

# 2. dev3 m3 기동 (Code-Shepherd-new 루트)
cd C:\Users\user\Code-Shepherd-new
docker compose up -d m3

# 3. 구 스택 m3 정지 유지, old stack 기동
cd C:\Users\user\Code-Shepherd  # (구 팀 스택 경로)
docker compose up -d

# 4. 네트워크 브리지 (컨테이너 재시작마다 필요)
docker network connect --alias m3 code-shepherd_code-shepherd code-shepherd-new-m3-1

# 5. 캐시 워밍 1회
docker exec code-shepherd-m1-1 python /app/service/_send_test_webhook.py
```

### 핫스왑 절차 (통합 환경)

```bash
# 1. 호스트에서 corpus 수정
copy fixtures\demo\hotswap_external_api.md corpus\external_api.md

# 2. 컨테이너 내 reindex
docker exec code-shepherd-new-m3-1 python -m src.ingestion

# 3. 재실행 → 판정 변경 확인
docker exec code-shepherd-m1-1 python /app/service/_send_test_webhook.py

# 4. 원복
git checkout corpus/
docker exec code-shepherd-new-m3-1 python -m src.ingestion
```

---

## 사전 체크리스트 (시연 5분 전)

- [ ] Ollama 기동 (`http://localhost:11434` — bge-m3 확인: `ollama list`)
- [ ] Docker Desktop 기동 + 전체 스택 상태 확인
- [ ] `code-shepherd-new-m3-1` 실행 중 + 네트워크 연결됨
- [ ] 캐시 워밍 1회: `docker exec code-shepherd-m1-1 python /app/service/_send_test_webhook.py`
- [ ] `ENABLE_DB_WRITE=false` 확인 (`.env` 기본값)
- [ ] 프론트 http://localhost:5173 접근 가능 확인
- [ ] **폴백 준비**: Streamlit `make demo` (m3 직접실행 — 팀 스택 불필요)
- [ ] 녹화 백업 준비

## 장면1 — 위반 탐지 (3분)

| 항목 | 내용 |
|---|---|
| 입력 | 사이드바 "시연 장면 선택" → **장면1** (`fixtures/demo/scene1_violation.txt`) — async 결제 서비스 안 동기 `requests` |
| 예상 출력 | 타임라인 ⓪→⑤ 전부 ✅ · **[CONV-API-001] violation ×2 (Major)** · 「2025-11 블랙프라이데이 사고」 §1 원문 인용 + [출처](corpus/external_api.md) 링크 · 인용 검증 전부 OK (환각 0) |
| 소요 | 캐시 히트 ~5초 / 콜드 ~25초 |
| 멘트 | "모든 지적은 사내 규칙 원문을 그대로 인용하고, string-match로 환각을 자동 검증합니다." |

## 장면2 — 오탐 회피: 예외조항 (2분)

| 항목 | 내용 |
|---|---|
| 입력 | **장면2** (`fixtures/demo/scene2_exception.txt`) — `scripts/` 배치 코드의 같은 requests 패턴 |
| 예상 출력 | **지적 없음 (정상)** — §4 예외조항(scripts/·batch/ 제외) 적용 |
| 소요 | ~5초 (캐시) |
| 멘트 | "같은 패턴이라도 예외조항을 읽고 오탐을 내지 않습니다. 골든셋 오탐 0건." |

## 장면3 — 지침공백 정직 보고 (3분)

| 항목 | 내용 |
|---|---|
| 입력 | **장면3** (`fixtures/demo/scene3_gap.txt`) — subprocess 사용 (KMS에 규정 없음) |
| 예상 출력 | 타임라인 ③ route=requery → ③ route=gap_report · **지침공백 리포트**: 시도한 질의 목록 + 근접 규칙 + **신규 지침 제안 초안** (CONV-XXX 마크다운) |
| 소요 | ~10초 (재질의 1회 포함) |
| 멘트 | "모르면 지어내지 않고 모른다고 보고합니다. 그리고 빈 자리를 채울 지침 초안까지 제안합니다." |

## 장면4 — 핫스왑 (5분) ★리허설 실측

| 단계 | 명령/행동 | 실측 |
|---|---|---|
| ① baseline | 장면4 (`scene4_hotswap.txt` — `httpx.AsyncClient`) 실행 → **지적 없음 (정상)** | ~5초 |
| ② 스왑 | `copy fixtures\demo\hotswap_external_api.md corpus\external_api.md` → Streamlit **make reindex 버튼** (httpx→aiohttp 표준 변경) | 17초 |
| ③ 재실행 | 같은 장면4 재실행 → **[CONV-API-001] violation (Major)** — "2026-06 표준화 이후 httpx 사용도 위반" 조항을 그대로 인용 | ~13초 |
| ④ 원복 | Streamlit **핫스왑 원복 버튼** (= `git checkout corpus/ && make reindex`) | ~17초 |
| 멘트 | "코드 한 줄 안 바꿨습니다. 지침 문서가 바뀌면 판정이 바뀝니다 — 에이전트의 두뇌가 KMS에 있다는 증거입니다." |

원복 후 (발표 뒤): `make eval` 12/12 재확인 — D5 리허설에서 검증 완료 (run_20260612-163506).

## 발표 수치 (게이트 4 — D5 박제)

| 지표 | 결과 |
|---|---|
| 탐지율 | 6/6 (100%) |
| 오탐 | 0건 (정상 4 PR) |
| 환각률 | 0% (rule_id 실존 + rule_quote·evidence string-match) |
| 지침공백 정확도 | 2/2 (100%) |
| 전체 | **12/12 PASS** · 임베딩 bge-m3(1024d) 기준 |
