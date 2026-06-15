# Dev3 코드리뷰 에이전트 — 5일 MVP 킥오프 브리프

> 이 문서는 Claude Code 세션의 마스터 지시문이다. 충돌 시 이 문서가 우선한다.
> 목표: PR diff를 받아 사내 KMS 컨벤션에 **근거해서만** 리뷰 코멘트를 다는 에이전트.
> 차별점 3가지를 시연으로 증명한다 — ①KMS 근거 인용 ②지침 없으면 "지침공백" 정직 보고 ③지침 수정 시 코드 변경 없이 판정이 바뀜(핫스왑).

---

## 0. 시작 전 정현 준비 체크리스트 (D1 오전 전까지)

- [ ] LLM API 키 확보 + 일일 한도 확인 (시연 당일 한도 초과 = 사고)
- [ ] 임베딩 모델 결정 → [결정요청 #1] 참조 (기본안: OpenAI text-embedding-3-small, 한국어 문서 대응)
- [ ] GitHub PAT 발급 (scope: repo — PR read + comment write), 데모 타깃 repo 지정
- [ ] 기존 웹훅 + ngrok 코드 경로/실행 방법 메모 → Claude Code에 그대로 전달
- [ ] 기존 AST(N+1 탐지) 코드 경로 확인 (D4 stretch용)
- [ ] Python 3.11+ 가상환경, Streamlit 설치 가능 확인
- [ ] (선택) LangSmith 키 — 트레이싱. 없으면 콘솔 로깅으로 대체
- [ ] 발표용 노트북에서 ngrok + 로컬 서버 사전 구동 테스트 (행사장 와이파이 제약 확인)
- [ ] 실제 팀/부트캠프에서 들은 코딩 규칙 2~3개 메모 → 컨벤션 코퍼스의 현실성 재료

## 1. 팀원 공유 사항 (D1 중 전달)

1. **스코프 선언** (그대로 전달 가능):
   "Dev3 리뷰 에이전트는 D+5 시연까지 **단독 MVP**로 진행한다. 자체 미니 KMS(마크다운 규칙 5~8개 + 로컬 벡터스토어)를 사용하며, 팀 KMS·오케스트레이터 통합은 시연 이후 v2 범위다. MVP 기간 중 통합 요청은 받지 않는다."
2. **인터페이스 계약 공유** → 오케스트레이터/통합 담당자에게:
   - 입력: `{diff: str, file_paths: list[str], repo_meta: dict}`
   - 출력: `{findings: list[Finding], comment_md: str, gap_report: dict | null}`
   - v2에서 이 스키마로 붙으면 됨. MVP 중 스키마 변경 없음.
3. **KMS 문서 포맷 합의** → 문서/KMS 담당 팀원과 템플릿 통일 (v2 통합 비용 절감):
   - 규칙 문서: `rule_id`, `severity(Major/Minor/Info)`, §단위 본문, 올바른/잘못된 예시 코드, 예외 조항
4. **GitHub 권한**: org repo 사용 시 웹훅 설정 권한 + 데모 PR 생성 권한 요청
5. **시연 슬롯 확보**: 4장면 약 5~7분 + 핫스왑 라이브 시간. 발표 순서에 반영 요청
6. **수치 정의 합의**: "탐지율 6/6, 오탐 0"의 분모(골든셋 구성)를 팀 발표 자료와 일치시킬 것

## 2. 운영 모델 — "결정 패키지" 방식 (중요)

Claude Code는 **모든 판단 영역에서 먼저 스스로 분석하고, 결정 패키지를 제출한다.** 정현은 승인/수정/거부만 한다.

### 2.1 결정 패키지 포맷 (이 형식 강제)

```
[결정요청 #N] 제목
A) 옵션 — 장점 / 단점
B) 옵션 — 장점 / 단점
추천: X (근거 1~2문장)
리스크: 1문장 + 완화책
되돌리기 비용: 낮음/중간/높음
→ 무응답 데드라인: D? HH:00 — 경과 시 추천안으로 진행
```

### 2.2 승인 게이트 (이 4가지만 무응답 진행 금지, 명시적 승인 필수)

1. 골든셋 라벨 변경/추가/삭제
2. 계약 스키마(State, 노드 I/O, 입출력) 변경
3. 스코프 추가 (새 기능, 새 의존성 도구)
4. 발표용 수치의 해석/주장 문구

### 2.3 그 외 전부 — 기본값 선진행 원칙

게이트 4종 외의 모든 것은 **합리적 기본값으로 즉시 진행**하고, 결정 패키지는 사후 보고 또는 튜닝 시점(D3)에 묶어서 올린다. 사소한 것까지 결정요청 올리는 것 금지 — 결정 대기가 5일 일정의 최대 적이다.

### 2.4 "정현 직접" 항목의 결정 패키지 전환표

| 항목 | Claude Code가 준비하는 것 | 정현이 하는 것 |
|---|---|---|
| 계약 동결 | State/노드 I/O/입출력 스키마 완성안 + 대안 1개 | 승인 (D1 오전) |
| 컨벤션 코퍼스 | 규칙 5~8개 완성 초안 + 시연 장면 매핑표 | 현실성 검수, 2~3개는 본인 메모 반영 |
| 골든셋 라벨 | PR 12개 + 기대 라벨 초안 | 라벨 전수 확인 (유일하게 전수 검수) |
| 판정 프롬프트 튜닝 | 실패 케이스 원인 분류 + 수정안 A/B | D3에 A/B 중 선택 |
| 웹훅 go/no-go | D1 90분 타임박스 점검 결과 + 권고 | go/no-go 결정 |
| 시연 수치 | 측정 결과 + 주장 가능한 문구 후보 | 문구 확정 (게이트 4) |
| 발표 내러티브 | 4장면 시나리오 스크립트 초안 | 수정·리허설 |

### 2.5 애매 항목 처리 방침 (확정)

- **개념추출 동의어 수**: 기본 3개/개념으로 진행 → D3에 recall 보고 후 조정 결정요청
- **충분성 판단**: 기본 = top-k 5, LLM relevance 판정(yes/no), 재질의 1회 상한 → D3 튜닝
- **코멘트 톤/템플릿**: 기본안 1개로 진행 → D4 시연 빌드 때 정현 리뷰 1회
- **AST 도구**: D4 14:00 기준 D4 태스크 완료 시에만 go. 미완이면 자동 컷 (결정요청 불필요)
- **웹훅**: D1 90분 타임박스. 아래 3개 전부 통과 못 하면 자동 no-go → Streamlit 단독
  - [ ] payload에 diff(또는 diff 조회 가능한 정보) 포함
  - [ ] PAT로 PR 코멘트 POST 성공
  - [ ] ngrok 터널 30분 유지 확인

## 3. 기술 스펙 (동결 대상)

- **스택**: Python 3.11+, LangGraph(버전 고정 — requirements.txt에 명시), Chroma(로컬, 도커 불필요), Streamlit, OpenAI/Anthropic API
- **컷 확정**: Neo4j, Postgres, GitHub Actions, 멀티 에이전트 통합 — 전부 v2. MVP에서 언급 금지
- **노드 6개 파이프라인**:

| # | 노드 | 입력 | 출력 | 단위테스트 기준 |
|---|---|---|---|---|
| ⓪ | assemble_input | diff, file_paths, repo_meta | State.pr_context (diff + 변경 파일 전문) | 샘플 payload → 스키마 검증 통과 |
| ① | extract_concepts | pr_context | concepts[{name, synonyms[3]}], queries[] | 고정 diff → 핵심 개념 1개 이상 + 동의어 3개 |
| ② | retrieve | queries | chunks[{rule_id, section, text, severity, score}] (top-k 5/query, dedup) | 시드 코퍼스에서 정답 rule_id 검색됨 |
| ③ | check_sufficiency | chunks, pr_context | route: proceed / requery(1회) / gap_report | 빈 결과 → gap, 정답 포함 → proceed |
| ④ | judge | chunks, pr_context | findings[{rule_id, verdict, evidence_lines, severity, fp_note}] | 위반 PR → violation, 정상 PR → no_violation |
| ⑤ | compose_comment | findings 또는 gap | comment_md (출처 링크 포함) / 지침공백 리포트 + 신규지침 제안 | 코멘트에 rule_id 인용 + 인용 문구가 코퍼스에 실존 |

- ④ judge는 단일 CoT 프롬프트 내부에 [검사계획 수립 → 조항-코드 대조 → 오탐 점검] 3단계를 포함. 별도 노드로 쪼개지 말 것.
- ③ requery는 전 파이프라인에서 최대 1회. 카운터를 State에 둘 것.

## 4. 골든셋 & 평가 하네스 명세

### 4.1 골든셋 구조 (수정 금지 디렉토리)

```
golden/
  pr_001/
    diff.patch
    files/            # 변경 파일 전문
    label.yaml        # expected: [{rule_id, verdict}] 또는 expected: []  또는 expected: gap
```

- 구성: 위반 6 (이 중 1개는 예외조항 적용으로 '정상' 판정돼야 함 — 오탐 회피 데모용), 정상 3, 지침공백 2
- **golden/ 과 contracts/ 는 Claude Code 수정 금지. 테스트 실패 시 코드를 고친다. 골든셋을 고치지 않는다.** (변경 필요 시 게이트 1 결정요청)

### 4.2 지표 (하네스가 자동 출력)

- 탐지율: 위반 PR 중 올바른 rule_id로 잡은 비율
- 오탐: 정상 PR에 violation 낸 건수
- **환각률 (자동 검증 가능)**: 코멘트가 인용한 rule_id가 코퍼스에 실존하는지 + 인용 문구가 해당 청크에 string-match 되는지. 이 검증 코드를 하네스에 반드시 포함
- 지침공백 정확도: gap PR 2개를 gap으로 보고했는지

### 4.3 실행

- `make eval` 한 줄로 골든셋 전체 실행 → 표 형태 리포트. temperature 0 고정
- eval 실패 로그는 JSON으로 저장 → 원인 분류는 Claude Code가 수행 후 보고

## 5. Repo / Git 운용

### 5.1 디렉토리 골격

```
dev3-review-agent/
  CLAUDE.md
  contracts/          # 스키마 정의 (수정 금지, 게이트 2)
  corpus/             # KMS 컨벤션 마크다운 5~8개
  golden/             # 골든셋 (수정 금지, 게이트 1)
  src/
    nodes/            # 노드별 1파일
    graph.py          # LangGraph 조립
    adapters/         # webhook_adapter.py, streamlit_adapter.py
    ingestion.py      # corpus → chunk → embed → Chroma. 원커맨드 재인덱싱 (핫스왑용)
  eval/harness.py
  app/streamlit_app.py
  examples/langgraph_reference.py   # 공식 예제 — 버전 함정 방지용, 항상 이 문법 기준
  tests/
  Makefile            # make eval / make reindex / make demo
```

### 5.2 worktree 운용 (D1~D2만 병렬, D3부터 단일 라인)

```bash
# 메인 세션: 파이프라인 (정현 주도)
# 세션 B: 하네스 + Streamlit 껍데기
git worktree add ../dev3-harness -b feat/harness
# 세션 C: ingestion + 코퍼스 초안
git worktree add ../dev3-ingestion -b feat/ingestion

# D2 말 통합 후 제거
git worktree remove ../dev3-harness
git worktree remove ../dev3-ingestion
```

- 동시 세션 상한 3 (메인 포함). 세션 간 공유 파일은 contracts/ 뿐 — 그래서 계약 동결이 D1 오전인 것
- 커밋 작게: 노드 1개 = 커밋 1개 이상. 머지는 정현 확인 후

### 5.3 CLAUDE.md에 반드시 포함할 내용

1. 프로젝트 한 줄 설명 + 이 브리프 파일 참조
2. 계약 스키마 위치(contracts/), 실행·테스트 명령(make eval 등)
3. **수정 금지: golden/, contracts/** + 승인 게이트 4종
4. 결정 패키지 포맷 + 기본값 선진행 원칙 (§2 복사)
5. LangGraph 버전 고정 + examples/langgraph_reference.py 의 `interrupt()`/`Command` 문법만 사용
6. temperature 0, 모든 LLM 호출에 모델명·프롬프트 버전 로깅

## 6. 일자별 플랜

| Day | 메인 세션 | 병렬 세션 | 정현 |
|---|---|---|---|
| D1 | repo 골격, CLAUDE.md, contracts/ 동결, 웹훅 90분 점검 | B: 하네스 골격+Streamlit 껍데기 / C: 코퍼스·골든셋 초안+ingestion | 계약 승인, 코퍼스 검수, 골든셋 라벨 전수 확인, 웹훅 go/no-go, 팀 공유 |
| D2 | ⓪~⑤ 직선 E2E (분기·루프 없이) | B,C 통합 → worktree 제거 | E2E 1케이스 확인, 첫 측정 리뷰 |
| D3 | ③ 분기·재질의·gap 경로 + 프롬프트 튜닝 루프 | — | 실패 케이스 A/B 결정, 임계값 결정 |
| D4 | Streamlit 완성, 핫스왑(make reindex), 웹훅 연결(go시), 최종 측정 | — | 코멘트 톤 리뷰, AST go/no-go(14:00), 수치 문구 확정 |
| D5 | 버그픽스만. **기능 추가 금지** | — | 시연 4장면 리허설 2회, 녹화 백업, 발표 자료 |

## 7. 시연 4장면 (발표 순서 고정)

1. 위반 탐지 — async 함수 내 requests → 「외부 API 호출 컨벤션 §2」 인용 코멘트 (라이브: 웹훅 go면 실제 PR에 코멘트, no-go면 Streamlit)
2. 오탐 회피 — scripts/ 배치 코드, 같은 패턴이지만 예외조항 적용 → 미지적 또는 Info
3. **지침공백 정직 보고** — KMS에 없는 패턴 → 지어내지 않고 gap 리포트 + 신규 지침 제안
4. **핫스왑** — corpus 문서 "httpx → aiohttp" 수정 → `make reindex` → 같은 PR 재실행 → 판정 변경. "코드 한 줄 안 고치고 검사가 바뀝니다"

발표 메시지: 3·4가 주인공. "일반 코드리뷰 AI는 세상 기준으로 보고, 이 에이전트는 우리 회사 기준으로 본다. 그리고 모르면 모른다고 한다."

## 8. 금지사항 요약

- D5 기능 추가 금지 / golden·contracts 수정 금지 / 게이트 4종 무단 진행 금지
- 시연용 실행은 temperature 0 + 동일 입력 리허설 2회 + 녹화 백업 필수
- Neo4j·Postgres·팀 통합 관련 코드 작성 금지 (v2)

## 9. 비용 최적화 (우선순위 순)

1. **로컬 응답 캐시 (D2부터, 필수)**
   모든 LLM 호출을 sha256(모델명+프롬프트 전문) 키로 디스크 캐싱.
   temperature 0이라 동일 입력=동일 출력이므로 손실 없음.
   UI 테스트·시연 리허설·재실행이 전부 0원 + 결정적.
   프롬프트 바뀌면 해시가 달라져 자동 캐시 미스 — 무효화 로직 불필요.

2. **하네스 부분 실행 모드**
   make eval-failed (직전 실패 케이스만), make eval-one PR=pr_003.
   프롬프트 한 줄 수정마다 12개 전체 실행 금지.

3. **Anthropic 프롬프트 캐싱**
   노드 프롬프트 구조: [고정 프리픽스: 시스템+검사절차+출력스키마+few-shot]
   + [가변 서픽스: chunks+diff]. 프리픽스에 cache_control 적용.
   고정 부분이 반드시 앞에 와야 캐시 히트.

4. **입력 다이어트**
   judge 입력 청크: dedup 후 최대 6~8개 캡.
   파일 전문 대신 diff + 해당 함수 주변 컨텍스트만.
   노드별 max_tokens: judge 2000, 나머지 800.

5. **모델 다운그레이드 (D4, 조건부)**
   ⑤코멘트 생성부터 Haiku 4.5로 전환 후 골든셋 전체 재실행 통과 시 유지.
   ④judge는 Sonnet 4.6 고정 — 절대 다운그레이드 금지.
   D3 튜닝 완료 전 모델 변경 금지.

## [결정요청 #1] 임베딩 모델 (D1 오전 데드라인)

A) OpenAI text-embedding-3-small — 한국어 무난, 비용 미미, 외부 API 의존
B) bge-m3 로컬 — 무료·오프라인, 초기 다운로드 큼, 셋업 변수
추천: A (5일 일정상 셋업 리스크 최소화. 시연 중 API 장애는 임베딩 캐시로 완화)
되돌리기 비용: 낮음 (ingestion 재실행이면 끝)
→ D1 12:00 무응답 시 A로 진행
