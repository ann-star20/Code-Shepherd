# Task-Link — PPT 압축 버전 (4페이지)

---

## 1p | 프로젝트 소개 + 배경·목적

**Task-Link — AI 멀티 에이전트 기반 PR 코드 리뷰 자동화 플랫폼**

> 내 역할: Dev2 — 정적 분석 + 보안 스캔 에이전트 단독 설계·구현

### 프로젝트 정보

- 기간 / 인원: 2026년 5월 · 6주 · 6명 (FE 1 + 서비스 5)
- 기술 스택: Python · LangGraph · Claude API · pgVector · FastAPI · BigQuery · Airflow · LangSmith

### 배경 — 왜 만들었나

- 시니어 개발자, 신입 PR 리뷰에 **하루 1~2시간 소비**
- SQL 인젝션·N+1 쿼리 같은 **반복 실수에 매번 같은 피드백**
- PR 피드백 지연 → **개발 흐름 단절**, 성장 데이터 없음

### 목적

- AI가 PR diff 자동 분석 → severity 분류 → 즉시 피드백
- Critical 이슈 시니어에게 자동 에스컬레이션
- 반복 실수 패턴 데이터 누적 → BigQuery 성장 지표 정량화

### 기대 효과

| 항목 | 목표 |
|---|---|
| 시니어 리뷰 부담 | 70% 감소 |
| PR 피드백 속도 | 즉시 자동화 |
| 실수 패턴 | 데이터 정량화 |

---

## 2p | 문제-원인-해결 + 나의 액션

**"분석 도구는 있었지만, AI 판단과 연결하는 레이어가 없었다"**

### 문제 → 원인 → 해결

| 문제 | 원인 | 해결 |
|---|---|---|
| 반복 코드 이슈를 사람이 매번 확인 | CLI 도구가 CI에 통합 안 됨 | PR 수신 시 자동 분석 파이프라인 |
| 이슈 severity 기준이 주관적 | 도구 판단만으로는 context 부족 | RAG + LLM Judge로 severity 재판단 |
| 같은 실수 반복 학습 연결 안 됨 | 과거 이슈와 연결 체계 없음 | pgVector 유사 이슈 → LLM context 주입 |

### 나의 액션 (직접 구현)

- LangGraph 5-노드 Agentic Workflow — conditional edge로 Critical 시 실행 경로 자동 분기
- Python·JS·C#·HTML·CSS 7개 언어 도구 통합, Pydantic으로 통일 스키마 정규화
- pgVector RAG 유사 이슈 검색 (코사인 유사도 ≥ 0.7 → LLM context 주입)
- 비용 최적화 모델 라우팅: Critical→Sonnet / Major→Haiku / Minor→LLM 생략
- PostgreSQL(OLTP) + BigQuery(OLAP) 이중 적재 파이프라인
- Airflow DAG: 일일 ETL + 주간 리포트 자동 스케줄링
- LangSmith 트레이싱: 전 에이전트 실행 이력 추적 (AI Observability)
- USE_MOCK_LLM 설계: 코드 변경 없이 Mock ↔ 실제 LLM 전환 → 팀 병렬 개발 실현

### 핵심 시행착오

> asyncio.TimeoutError를 `async with` 블록 안에서 잡으면 DB에 'success'가 기록되는 버그 발견 → try/except를 블록 바깥으로 이동 + 팀 전체 규칙으로 문서화

---

## 3p | 결과물 + 성장한 점

**Dev2 단독 구현 전체 완료 — E2E 테스트 통과**

### 구현 파이프라인

```
GitHub PR diff 수신
  → run_tools        (Bandit·Pylint·ESLint·Semgrep 병렬, 7개 언어)
  → vector_search    (pgVector RAG 유사 이슈 검색)
  → llm_judge        (Claude severity 재판단 + 모델 라우팅)
  → escalate / store (Critical 조건부 분기 → Dev4 webhook)
  → PostgreSQL + BigQuery 이중 적재
  → LangSmith 트레이싱 자동 기록
```

### 완성물

- FastAPI: `POST /scan`, `GET /insights`, `GET /issues`, `PATCH /dismiss`
- Airflow DAG: 일일 ETL + 주간 개발자별 실수 패턴 리포트
- scan_executions → scan_issues → scan_summaries 3-테이블 구조

### 성장한 점

- **기술**: LangGraph Agentic Workflow · RAG 파이프라인 · asyncio 에러 격리 · LangSmith Observability · Airflow DAG
- **설계**: 에러 케이스 먼저 정의 → fallback 선 구현 방식으로 사고 전환
- **협업**: Pydantic Output Contract 명문화 + Mock 전환 설계 → 팀 6명 병렬 개발 실현
- **비즈니스**: 기술 선택을 비즈니스 목표(시니어 시간 절약)에서 역산, AI 비용을 설계 단계에서 통제

---

## 4p | 역량·기여 + 면접 한 줄 어필

**AX/DX 직무에서 이 경험이 직결되는 이유**

### 역량 → 직무 연결

| 역량 | 프로젝트 근거 | 직무 기여 |
|---|---|---|
| AI 파이프라인 설계 | LangGraph Agentic Workflow end-to-end | AI 내재화 과제 직접 설계·실행 |
| 업무 자동화 전환 | 수동 리뷰 → 자동 분석+에스컬레이션 | 반복 업무의 AI 전환 기획 |
| 데이터 기반 의사결정 | BigQuery + Airflow 분석 파이프라인 | 성과 측정 지표 설계 |
| AI 비용 최적화 | 모델 라우팅으로 비용 구조 설계 | LLM 도입 TCO 관리 |
| AI 시스템 운영 | LangSmith Observability 설계 | AI 품질 모니터링 체계 구축 |
| 협업 설계 | Mock 전환 + Pydantic Contract | 팀 AI 도입 인터페이스 설계 |

### 면접 한 줄 어필

> "AI를 도구로 쓰는 것에 그치지 않고, AI 판단이 업무 프로세스의 실행 경로 자체를 바꾸는 Agentic Workflow를 설계·구현했고, Observability와 비용 통제까지 처음부터 설계한 경험이 있습니다. AX/DX 현장에서 AI 내재화 과제에 바로 기여할 수 있습니다."
