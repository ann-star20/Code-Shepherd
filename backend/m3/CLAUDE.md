모든 응답은 한국어로. 코드·변수명·커밋메시지는 영어 유지.
# Dev3 코드리뷰 에이전트 — 작업 지침 (CLAUDE.md)

PR diff를 받아 **사내 KMS 컨벤션에 근거해서만** 리뷰 코멘트를 다는 에이전트의 5일 MVP.
마스터 지시문: **[DEV3_MVP_KICKOFF.md](DEV3_MVP_KICKOFF.md)** — 이 파일과 충돌 시 브리프가 우선한다.

## 계약·실행 명령

- 계약 스키마: `contracts/schemas.py` + 노드 I/O 표는 `contracts/README.md`
- 실행:
  - `make eval` — 골든셋 전체 평가 (표 리포트, temperature 0)
  - `make eval-one PR=pr_003` / `make eval-failed` — 부분 실행 (비용 절약, 브리프 §9.2)
  - `make reindex` — corpus → Chroma 재인덱싱 (핫스왑 시연용 원커맨드)
  - `make demo` — Streamlit 실행
  - Windows에 make 없으면 동일 타깃의 `.\make.bat eval` 사용
- 환경: `.venv` (Python 3.13), 키는 repo 루트 `.env` — ANTHROPIC_API_KEY, OPENAI_API_KEY, GITHUB_TOKEN, GITHUB_WEBHOOK_SECRET
- **키 값을 코드·로그·커밋·채팅에 절대 출력하지 않는다. `.env` 커밋 금지 (.gitignore 처리됨).**

## 수정 금지 + 승인 게이트 4종

- **`golden/` 과 `contracts/` 는 수정 금지.** 테스트 실패 시 코드를 고친다. 골든셋·계약을 고치지 않는다.
- 아래 4가지는 결정 패키지 제출 후 **명시적 승인 없이는 진행 금지** (무응답 진행 불가):
  1. 골든셋 라벨 변경/추가/삭제
  2. 계약 스키마(State, 노드 I/O, 입출력) 변경
  3. 스코프 추가 (새 기능, 새 의존성 도구)
  4. 발표용 수치의 해석/주장 문구

## 운영 모델 — 결정 패키지 (브리프 §2 요약)

모든 판단 영역에서 먼저 스스로 분석하고 결정 패키지를 제출한다. 정현은 승인/수정/거부만 한다.

```
[결정요청 #N] 제목
A) 옵션 — 장점 / 단점
B) 옵션 — 장점 / 단점
추천: X (근거 1~2문장)
리스크: 1문장 + 완화책
되돌리기 비용: 낮음/중간/높음
→ 무응답 데드라인: D? HH:00 — 경과 시 추천안으로 진행
```

**게이트 4종 외 전부 기본값 선진행**: 합리적 기본값으로 즉시 진행하고 사후 보고(또는 D3 튜닝 시점에 묶음 보고). 사소한 결정요청 남발 금지 — 결정 대기가 5일 일정의 최대 적이다.

## LangGraph 규칙

- 버전 고정: `requirements.txt` 의 `langgraph==` 핀 외의 버전 문법 사용 금지
- **`examples/langgraph_reference.py` 의 문법만 사용** (`interrupt()`/`Command` 포함). 기억 속 다른 버전 API·블로그 문법 금지.
- 노드 6개 직선 파이프라인 + ③의 조건 분기만. ④ judge 를 여러 노드로 쪼개지 않는다.

## LLM 호출 규칙

- **temperature 0 고정. 전 노드 `claude-sonnet-4-6`** (모델·프롬프트 버전은 `src/config.py` 한 곳에서만 관리 — 노드 코드에 하드코딩 금지)
- 모든 LLM 호출에 **모델명 + 프롬프트 버전 로깅**
- 임베딩: OpenAI `text-embedding-3-small` ([결정요청 #1] 승인안 A)
- D2부터 디스크 캐시 필수: `sha256(모델명 + 프롬프트 전문)` 키 (브리프 §9.1)
- 프롬프트 구조: [고정 프리픽스: 시스템+검사절차+출력스키마+few-shot, cache_control] 앞 + [가변: chunks+diff] 뒤 (브리프 §9.3)
- max_tokens: judge 2000, 나머지 800. judge 입력 청크 dedup 후 6~8개 캡 (브리프 §9.4)
- D3 튜닝 완료 전 모델 변경 금지. ④ judge 는 영구적으로 다운그레이드 금지 (브리프 §9.5)

## 세션 경계 (D1~D2 병렬, 충돌 방지)

| 세션 | 브랜치 | 소유 경로 |
|---|---|---|
| 메인 (파이프라인) | main | `src/nodes/`, `src/graph.py`, `src/adapters/`, `src/llm.py`, `src/config.py` |
| B (하네스+UI) | feat/harness | `eval/`, `app/`, `tests/test_harness*.py` |
| C (코퍼스+인제스천) | feat/ingestion | `corpus/`, `golden/`(초안), `src/ingestion.py` |

세션 간 공유 파일은 `contracts/` 뿐이며 읽기 전용. **다른 세션 소유 경로를 수정하지 않는다.** D2 말 통합 후 worktree 제거.

## 금지사항 (브리프 §8)

- D5 기능 추가 금지 / Neo4j·Postgres·GitHub Actions·팀 통합 코드 작성 금지 (전부 v2)
- 시연용 실행은 temperature 0 + 동일 입력 리허설 2회 + 녹화 백업 필수

## 통합 불변조건
- 우리는 팀 스택의 m3를 대체한다. 호출자 m1(api-core), 포트 8004, 계약 M3ReviewRequest/Response.
- 팀 파일 수정 절대 금지: docker-compose.yml, backend/api-core, backend/m0, frontend
- golden/·contracts/ 수정 금지. judge 프롬프트는 eval 12/12 통과 상태에서 임의 변경 금지.
- 임베딩 기본 bge-m3(ollama, 1024d), openai(1536d)는 폴백.
- 환경 전환은 .env만으로: 직접실행=localhost, 도커=host.docker.internal
- DB 쓰기는 ENABLE_DB_WRITE=true일 때만. eval 중 INSERT 금지.