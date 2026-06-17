# INTEGRATION PLAYBOOK — code_review_agent를 팀 스택 m3로 통합

> 이 문서는 통합 세션의 마스터 지시문이다. Task 순서대로 진행하고, 각 Task 완료마다 보고한다.
> Task 1 완료 후에는 **반드시 정지하고 정현 승인**을 받는다. 그 외 Task는 자동 진행.

5. 커밋·푸시는 feat/m3-dev3-integration만. dev 머지 전 반드시 git fetch origin dev → merge → 충돌 확인 → 보고. dev 직접 push 금지.> 막히면 임의로 우회하지 말고 정지 + 보고.

## 절대 규칙

1. **팀 파일 수정 금지**: docker-compose.yml, backend/m0·m1·m2·m4·m5, api-core, frontend, _shared — 전부 읽기 전용. 유일한 예외는 backend/m3/ 교체와 docker-compose.override.yml **신규 추가**.
2. 키·접속정보 값을 채팅/로그/커밋에 절대 출력하지 않는다.
3. 우리 소스 정본: `C:\Users\user\새 폴더\code_review_agent` — 읽기만, 수정 금지.
4. 참고 문서 (먼저 정독): 정본 repo의 `docs/INTEGRATION_GUIDE.md`, `docs/INTEGRATION_READINESS.md`, `CLAUDE.md`의 통합 불변조건.

## 사전 준비 (정현 직접 — 세션 시작 전)

- [ ] Docker Desktop 실행 중
- [ ] Ollama 실행 중 + `ollama list`에 bge-m3 확인
- [ ] 팀 repo URL 확보 (Task 0의 {https://github.com/ann-star20/Code-Shepherd.git} 교체)
- [ ] 메인 세션의 DB 컬럼 수정이 **커밋·푸시 완료**된 상태인지 확인 (이식 대상은 최신본이어야 함)

---

## 보수 운영 프로토콜 (영구)

1. 팀 규약이 불명확하거나 우리 방식과 충돌하면: 임의 판단 금지. A/B 옵션 + 추천 + 영향 범위로 결정요청 올리고 정지.
2. 수정 가능 범위는 딱 셋: `backend/m3/**`, `docker-compose.override.yml`(신규), `.env`(항목 추가만). 그 외 팀 파일은 한 줄도 수정 금지.
3. m3 외 컨테이너가 안 뜨면: 수정 시도 금지, 로그 요약 보고만 (팀 소관).
4. 모든 커밋은 `feat/m3-dev3-integration`에만. 커밋 직전 `git status`로 의도치 않은 팀 파일 변경이 0건인지 확인 후 커밋.
5. 실패 보고 형식: 원인 추정 + 옵션 + 추천. 같은 지점에서 추측 수정 2회 실패하면 무조건 정지.
6. dev 브랜치는 움직이는 타깃 — PR 전 `git fetch origin dev → merge → 충돌 보고`는 기존 Git 규칙대로.

---

## 보정 사항

### 보정 1 — override build 규약

팀 원본 컨텍스트 유지: `context: ./backend`, `dockerfile: m3/Dockerfile`. `image:` 태그는 별칭으로만 사용.

```yaml
services:
  m3:
    image: dev3-m3:latest   # 태그만 — build context는 팀 규약 유지
    build:
      context: ./backend
      dockerfile: m3/Dockerfile
```

팀 규약과 다른 빌드 구조 금지.

### 보정 2 — compose 병합 함정

override는 base를 **대체가 아니라 병합**한다. base의 volumes(`./backend/m3:/app/service`, `/app/service/.venv`)가 살아있다는 전제로:

- Task 3에서 컨테이너가 실행하는 코드가 **이미지 베이크본인지 마운트본인지** 확인해서 보고.
- 핫스왑 요건 검증 필수: 호스트에서 `backend/m3/corpus` 수정 → 컨테이너 reindex → 판정 변경 반영. 안 되면 마운트 정렬안을 A/B 결정요청으로 올리고 정지.

### 보정 3 — 팀 설정 삭제 금지

base의 `_shared:ro` 마운트는 우리가 안 써도 무해하므로 유지. override에서 팀 설정을 "제거"하는 행위 전반 금지 — **추가와 대체만 허용**.

---

## Task 0 — 클론 + 사전 점검

1. `git clone {https://github.com/ann-star20/Code-Shepherd.git} C:\Users\user\new`
2. 우리 정본 repo에서 `git log -1`로 최신 커밋 확인 — DB 컬럼 수정 커밋이 포함돼 있는지. 없으면 정지+보고.
3. 정본 repo의 INTEGRATION_GUIDE.md / INTEGRATION_READINESS.md 정독, 핵심 절차 요약 보고.
4. 팀 repo의 .env.example(있다면)과 우리 .env 필요 키 대조 → **정현이 직접 채워야 할 .env 항목 목록** 보고 (값은 정현이 입력).

## Task 1 — 구조 대조 (읽기 전용) → 보고 후 정지 ⛔

1. 팀 `backend/m3/` 규약 파악: 폴더 구조, 진입점(`app.main:app`), Dockerfile 작성 방식, `_shared` 마운트 사용 방식, 포트 8004.
2. 우리 code_review_agent 구조와 차이 대조표 작성.
3. 이식 계획 보고: 우리 코드를 m3 규약에 맞추기 위해 바꿀 것 (진입점 래핑, import 경로, requirements↔uv 등).
4. **여기서 정지. 정현 승인 후 Task 2.**

## Task 2 — 이식

1. 팀 `backend/m3/` 내용을 `backend/m3_original/`로 이동 (삭제 금지 — 롤백용).
2. 우리 code_review_agent를 `backend/m3/`에 규약 맞춰 배치:
   - 진입점: `app/main.py`에서 http_adapter의 FastAPI app을 `app` 이름으로 노출
   - golden/, eval/, tests/ 포함 (통합 후에도 make eval 가능해야 함)
   - .env·.chroma 인덱스는 복사하지 않음 (인덱스는 Task 3에서 재생성)
3. `docker-compose.override.yml` 신규 작성 (팀 compose 본체 무수정):
   - m3 환경변수: EMBEDDING_PROVIDER=ollama, OLLAMA_BASE_URL=http://host.docker.internal:11434, ENABLE_DB_WRITE=false, ANTHROPIC_API_KEY 등 (env_file 경유)
   - 구 m3 전용 설정(RAG_ENABLED, hf_cache 볼륨)은 override로 무력화하거나 미사용 처리
4. .env 준비: 팀 .env에 우리 필요 키 항목 추가 (키 이름만 — **값은 정현이 직접 입력 후 "완료" 신호**).
5. 보고: 배치 결과 트리 + override 내용.

## Task 3 — m3 단독 기동 검증

1. `docker compose up -d m3` (또는 `docker compose up m3`)
2. `/health` 200 확인.
3. 컨테이너 안에서 reindex 1회 실행 (corpus 40청크, bge-m3 경유 — host.docker.internal:11434 연결 확인). 차원 1024 확인.
4. 스모크: POST /review 1건 (fixtures/demo/scene1) → findings 정상 + trace 포함 확인.
5. 컨테이너 안에서 make eval → **12/12 유지 확인**. 깨지면 정지+분류 보고.
6. 보고: health·reindex·스모크·eval 결과.

## Task 4 — 전체 스택 E2E (시연 경로 검증)

1. `docker compose up -d` 전체 (neo4j, m0~m5, api-core, frontend).
2. 기동 실패 컨테이너 있으면 목록+로그 요약 보고 (m3 외 컨테이너 문제는 **수정하지 말고 보고만** — 팀 소관).
3. 캐시 워밍: scene1 리뷰 1회 선실행 (m1 60초 타임아웃 대비).
4. 프론트 확인: http://localhost:5173 → PR 입력 → m1 → 우리 m3 → 결과 렌더 확인:
   - [ ] findings + 출처 인용 표시
   - [ ] trace 타임라인 (⓪→⑤) 렌더
   - [ ] finding 상세 펼침 (rule_quote·evidence·오탐체크)
5. RAG 확인: 코멘트가 KMS 규칙(rule_id·조항)을 정확히 인용하는지.
6. DB 적재 확인: ENABLE_DB_WRITE=true로 1회만 → review_issue INSERT → row 전체 덤프 (팀 표준 형식: keyword 한글 분류 / sub_category 영문 이슈명 / code_snippet·name_of_function 채워짐) → 즉시 false 복귀.
7. GitHub PR 코멘트: 데모 PR(-dev3-demo) 1건으로 웹훅 또는 POST /review 경유 코멘트 등록 확인.
8. 보고: 4~7 결과 + 스크린샷 안내 포인트.

## Task 5 — 시연 마감

1. `docs/INTEGRATION_E2E_REPORT.md`: Task 3~4 결과 집계 + 발견 이슈/잔여 리스크 목록.
2. DEMO_SCRIPT.md를 통합 환경 기준으로 갱신: 4장면 실행 경로 (프론트 주연, Streamlit 폴백), 핫스왑은 호스트 corpus 수정 → 컨테이너 reindex 절차로.
3. 시연 직전 체크리스트: Docker·Ollama 기동, 캐시 워밍 1회, ENABLE_DB_WRITE 상태, ngrok 고정 도메인, API 키 유효 확인.
4. 최종 보고.

---

## 실패 시 폴백 (각 Task 공통)

- Task 3 실패 → 정본 repo 직접 실행(비도커)으로 시연 가능 — 통합은 보고 후 정현 판단.
- Task 4에서 m3 외 컨테이너 문제 → 보고만, 프론트 시연은 m3+api-core+frontend 최소 구성으로 시도.
- 어떤 경우에도 Streamlit 단독 시연이 최종 폴백 (정본 repo에서 make demo).
