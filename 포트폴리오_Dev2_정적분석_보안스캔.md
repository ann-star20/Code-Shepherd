# Dev2 정적 분석 + 보안 스캔 에이전트 — 포트폴리오 정리 (STAR 기법)

---

## 01 프로젝트 소개 | AI 기반 PR 자동 코드 리뷰 에이전트

- **프로젝트 이름**: Task-Link — 조직 지식 관리 + 개발자 온보딩 멀티 에이전트 플랫폼
- **한 줄 소개**: PR diff를 자동 분석하여 정적 분석·보안 스캔·LLM 심각도 판단까지 수행하고, GitHub 코멘트·Slack 에스컬레이션까지 자동화하는 AI Native Agentic Workflow 구축
- **참여 인원 / 기간**: 6명 (FE 1 + 서비스 5) / 6주
- **내 역할**: Dev2 — 정적 분석 + 보안 스캔 에이전트 전체 설계·구현 (8개 LangGraph 노드, 6개 언어 지원 CLI 도구 통합, RAG 파이프라인, LLM 심각도 판단, GitHub/Slack 연동)
- **사용 기술**: Python, LangGraph (StateGraph), Claude API (Sonnet/Haiku 모델 라우팅), pgVector (RAG), FastAPI, asyncio, Pylint/Bandit/ESLint/Semgrep, PostgreSQL, BigQuery, GitHub API, Slack Webhook, Pydantic, pytest

---

## 02 프로젝트 개요 | 배경과 목적

- **배경**: 신입 개발자의 PR 코드 리뷰가 시니어 개발자에게 집중되어 리뷰 병목 발생. SQL 인젝션·XSS 같은 보안 취약점이 수동 리뷰에서 누락되는 리스크 존재.
- **문제**: 수동 코드 리뷰는 시니어 리소스를 과도하게 소모하고, 일관된 품질 기준 적용이 어려우며, 보안 이슈의 사후 발견 시 대응 비용이 급증.
- **AX/DX 관점**: CLI 도구(Pylint/Bandit/Semgrep) + LLM(Claude) + RAG(pgVector 과거 사례 검색)를 결합한 **AI 에이전트 파이프라인**으로 코드 리뷰 프로세스를 자동화하고, Critical 이슈 발생 시 즉시 에스컬레이션하는 **Human-in-the-Loop 의사결정 구조**를 구축.

---

## 03 진행한 일 | 배경-문제-해결

- **문제 상황**: 6인 팀에서 5개 에이전트가 병렬 개발되는 환경에서, 정적 분석 결과를 다른 에이전트(Dev4 평가)에 정확히 전달하고, 보안 취약점 발견 시 즉각적인 에스컬레이션이 필요했음.
- **핵심 원인**: 단순 CLI 도구 실행만으로는 심각도 판단의 일관성 부족. 과거 유사 사례 참조 없이는 오탐(false positive)률 개선이 어려움.
- **해결 방향**: CLI 도구 → RAG 유사 사례 검색 → LLM 심각도 재판단 → 조건부 에스컬레이션의 4단계 Agentic Workflow 설계.
- **내가 선택한 접근 방식**: LangGraph StateGraph로 8개 노드의 조건부 분기 그래프를 구축. LLM 판단 결과에 따라 실행 경로가 동적으로 변경되는 Agentic Workflow 패턴 적용.

---

## 04 과정 | 나의 직접적인 액션 + 인사이트

- **LangGraph 기반 8노드 파이프라인 설계·구현**: `run_tools → vector_search → llm_judge → [조건부] escalate → store → comment_generate → github_comment → [조건부] slack_notify`. Critical 이슈 유무에 따라 2개의 조건부 분기(conditional_edges)를 설계하여 단순 파이프라인이 아닌 AI 판단 기반 동적 워크플로우를 구현.

- **6개 언어 CLI 도구 통합 (asyncio 병렬 실행)**: Python(Pylint/Radon/Bandit), JavaScript(ESLint/npm-audit), C#(Roslyn), HTML(HTMLHint), CSS(Stylelint), 공통(Semgrep)의 정적분석·보안도구를 `asyncio.gather + asyncio.to_thread`로 병렬 실행. 언어별 30초 타임아웃과 에러 격리(`return_exceptions=True`)를 적용하여 한 도구의 실패가 전체 파이프라인을 중단하지 않도록 설계.

- **LLM 비용 최적화 모델 라우팅**: Critical → Claude Sonnet (정확도 우선), Major → Claude Haiku (비용 절감), Minor → LLM 생략 (CLI 판단 신뢰). 이슈 심각도별로 사용 모델을 분기하여 불필요한 API 호출을 제거.

- **RAG 파이프라인 구축 (pgVector 유사 사례 검색)**: 각 이슈의 메시지를 임베딩하여 pgVector에서 과거 유사 이슈를 검색하고, LLM 판단 시 context로 주입. 유사도 0.7 이상 / 상위 3건 필터링. Mock/실제 API 전환이 환경변수 하나로 가능하도록 설계.

- **OLTP+OLAP 이중 저장 설계**: PostgreSQL(운영 조회 — 빠른 단건)과 BigQuery(analytics DW — 추이 집계)에 동시 적재. PostgreSQL 실패 시 파이프라인 중단(핵심 기능), BigQuery 실패 시 로그 후 스킵(부가 기능)으로 장애 영향도를 차등 적용.

- **시행착오 — Mock/실제 전환 설계**: 6인 병렬 개발에서 DB·LLM·외부 API 없이도 각자 독립 개발·테스트가 가능해야 했음. `USE_MOCK_LLM` 환경변수 기반 Mock 패턴과 lazy import를 전 노드에 적용하여, 코드 변경 없이 `.env`만으로 Mock↔실제 전환 가능한 구조를 확보. 이 덕분에 Week 5 통합 시 코드 충돌 최소화.

- **인사이트**: 단순히 도구를 실행하는 것이 아니라, LLM 판단 결과에 따라 워크플로우 자체가 분기되는 "Agentic" 패턴이 업무 자동화의 핵심. 인간 개입 지점(HITL)을 명확히 정의하는 것이 자동화 시스템의 신뢰성을 결정.

---

## 05 결과물 | 최종 진행 내용 + 포인트

- **최종 결과물**: PR diff 입력 → 다국어 정적분석·보안 스캔 → RAG 유사 사례 검색 → LLM 심각도 재판단 → DB 적재 → GitHub PR 코멘트 자동 등록 → Critical 시 Slack 시니어 즉시 알림까지 완전 자동화된 8노드 LangGraph 파이프라인.

- **핵심 기능**:
  - 6개 언어 지원 (Python/JS/TS/C#/HTML/CSS)
  - LLM 모델 라우팅 (비용 최적화)
  - RAG 기반 과거 사례 참조 심각도 판단
  - Critical 이슈 자동 에스컬레이션 (GitHub 코멘트 + Slack 알림)
  - Pydantic 기반 Output Contract 검증 (에이전트 간 안전한 데이터 전달)

- **시스템 구조**: `FastAPI(진입점) → LangGraph StateGraph(8노드) → 조건부 분기(2개) → PostgreSQL + BigQuery 이중 적재 → GitHub API + Slack Webhook`

- **정량 성과**:
  - 8개 LangGraph 노드, 2개 조건부 분기 라우터 구현
  - 6개 언어 x 10종 CLI 도구 통합 (Pylint/Radon/Bandit/ESLint/npm-audit/Roslyn/HTMLHint/Stylelint/Semgrep/pip-audit)
  - 30+ 단위 테스트 (Mock 기반, DB/LLM 없이 통과)
  - LLM 호출 비용 절감: Minor 이슈 LLM 생략으로 전체 호출량 감소

- **정성 성과**:
  - 팀 공통 Output Contract JSON 계약 기반 협업 구조 확립
  - Mock/실제 전환이 환경변수 하나로 가능한 재현 가능한 파이프라인 구축
  - HITL(Human-in-the-Loop) 에스컬레이션 기준 수립 (Critical → 즉시 시니어 알림)

---

## 06 성장한 점

- **기술적 성장**: LangGraph StateGraph와 conditional_edges를 활용한 Agentic Workflow 설계 경험. 단순 순차 파이프라인이 아닌, AI 판단 결과에 따라 실행 경로가 동적으로 변경되는 시스템을 직접 구현.
- **문제 해결 방식**: asyncio 병렬 실행 시 에러 격리 패턴(return_exceptions), 타임아웃 처리, lazy import 등 실제 운영 환경에서 발생하는 엣지 케이스를 체계적으로 대응하는 방법 습득.
- **협업 방식**: 6인 병렬 개발에서 Output Contract(API 계약)와 Mock 서버 기반으로 다른 팀원의 구현 없이도 독립 개발·테스트가 가능한 구조를 설계. 이것이 통합 시 충돌을 최소화하는 핵심이었음.
- **비즈니스 이해**: 자동화 시스템에서 "어디까지 자동화하고, 어디서 사람이 개입해야 하는가"의 경계를 설계하는 경험. Critical 보안 이슈는 자동 머지하지 않고 시니어 에스컬레이션하는 HITL 설계가 비즈니스 리스크를 관리하는 핵심.

---

## 07 나의 역량 | 입사 시 기여할 수 있는 부분

- **AI 에이전트 파이프라인 설계·구현 역량**: LangGraph, Claude API, RAG(pgVector)를 결합한 Agentic Workflow를 직접 설계하고 운영 가능한 수준으로 구현한 경험.
- **업무 자동화 + 의사결정 자동화**: 단순 도구 실행이 아닌, AI 판단 기반으로 업무 흐름 자체를 자동 분기하는 시스템을 구축할 수 있음.
- **다국어·다도구 통합 경험**: 6개 프로그래밍 언어의 정적분석·보안 도구를 asyncio 병렬 실행으로 통합. 이기종 도구의 결과를 표준화하여 일관된 데이터 파이프라인으로 연결.
- **AX/DX 직무 적합성**: "기존 수동 업무 → AI 에이전트 기반 자동화 → 사람은 최종 의사결정만" 패턴을 직접 구현한 경험. 이 패턴은 코드 리뷰뿐 아니라 다양한 기업 업무에 적용 가능.

> **면접 어필 한 줄**: "CLI 도구의 결과를 LLM이 재판단하고, 그 판단에 따라 워크플로우가 동적으로 분기되는 AI Native 자동화 파이프라인을 LangGraph로 설계·구현하여, 코드 리뷰의 일관성 확보와 보안 이슈 즉시 대응 체계를 구축했습니다."

---

---

# 포트폴리오 PPT용 압축 버전 (3페이지)

---

## Page 1 — 프로젝트 소개 + Problem

### Task-Link: AI 기반 PR 자동 코드 리뷰 에이전트
> PR diff를 AI가 자동 분석하여 정적 분석·보안 스캔·심각도 판단·GitHub 코멘트·Slack 에스컬레이션까지 End-to-End로 자동화하는 Agentic Workflow

**프로젝트 개요**
| 항목 | 내용 |
|------|------|
| 팀 구성 | 6명 (FE 1 + 서비스 5) |
| 기간 | 6주 (설계 1주 + 개발 4주 + 통합 1주) |
| 내 역할 | Dev2 — 정적 분석 + 보안 스캔 에이전트 **전체 설계·구현** |
| 담당 범위 | LangGraph 파이프라인 설계, CLI 도구 통합, RAG 구축, LLM 판단, DB 적재, GitHub/Slack 연동 |

**Problem — 왜 이 프로젝트가 필요했는가**
- 신입 개발자의 PR 코드 리뷰가 시니어 개발자에게 집중 → **리뷰 병목** 발생
- 수동 리뷰는 리뷰어마다 기준이 달라 **일관성 부족** → 같은 이슈도 리뷰어에 따라 Pass/Reject 갈림
- SQL 인젝션, XSS 등 **보안 취약점이 수동 리뷰에서 누락** → 사후 발견 시 대응 비용 급증
- 기존 CI 린터는 "경고만 출력"할 뿐, **심각도 판단·에스컬레이션·사내 문서 연결**이 없음
- → AI가 분석·판단·알림까지 자동 수행하고, 사람은 최종 의사결정만 하는 **HITL 자동화** 필요

**Tech Stack**
| 분류 | 기술 |
|------|------|
| AI/LLM | LangGraph (StateGraph), Claude API (Sonnet/Haiku 모델 라우팅) |
| RAG | pgVector (코사인 유사도), OpenAI Embedding |
| Backend | FastAPI, Python 3.11+, asyncio, Pydantic |
| 분석 도구 | Pylint, Radon, Bandit, ESLint, npm-audit, Roslyn, HTMLHint, Stylelint, Semgrep, pip-audit |
| 저장소 | PostgreSQL (OLTP), BigQuery (OLAP) |
| 연동 | GitHub API (PR 코멘트), Slack Webhook (에스컬레이션) |
| 테스트 | pytest, unittest.mock (30+ 테스트) |

---

## Page 2 — 시스템 아키텍처 + 내가 한 일

### 전체 멀티 에이전트 시스템 (MAS) 구조
```
GitHub Webhook
    |
    v
[Dev1] Orchestrator — 의도 분류 + KMS 검색 (pgVector)
    |
    +------ asyncio.gather (병렬) ------+
    |                                    |
    v                                    v
[Dev2] 정적 분석 + 보안 스캔         [Dev3] 테스트 검증 + 성능 분석
    |                                    |
    +-------- 결과 취합 -----------------+
    |
    v
[Dev4] 3-Way 판정 (lgtm / rework / escalate)
    |
    v
[Dev5] 커리큘럼 + 반복 실수 패턴 감지
```

### 내 담당: Dev2 Agentic Workflow (8노드 LangGraph 파이프라인)
```
[1] run_tools          PR diff → 6개 언어별 CLI 도구 asyncio 병렬 실행
        |
[2] vector_search      이슈 메시지 임베딩 → pgVector 과거 유사 사례 검색 (RAG Retrieve)
        |
[3] llm_judge          유사 사례 context + 이슈 → Claude LLM 심각도 재판단 (RAG Generate)
        |
    [조건부 분기]       Critical >= 1? ← AI 판단 기반 동적 경로 결정 (Agentic 핵심)
     |          |
[4] escalate   |       Dev4에 즉시 HTTP 알림 (보안 이슈 긴급 전달)
     |          |
[5] store  <---+       PostgreSQL (OLTP) + BigQuery (OLAP) 이중 적재
        |
[6] comment_generate   개발자 수준(junior/mid/senior) 맞춤 PR 코멘트 LLM 생성
        |
[7] github_comment     GitHub PR에 마크다운 코멘트 자동 등록
        |
    [조건부 분기]       Critical >= 1?
     |          |
[8] slack_notify |     #team-security 채널 시니어 즉시 알림
     |          |
    END    <---+
```

**내가 직접 한 핵심 Action 5가지**

1. **Agentic Workflow 설계 (단순 파이프라인과의 차이)**
   - LLM 판단 결과(Critical 유무)에 따라 실행 경로가 동적으로 분기
   - 조건부 엣지 2개: `llm_judge → escalate/store`, `github_comment → slack_notify/END`
   - "도구 실행 → 결과 출력"이 아닌, "AI가 판단 → 워크플로우 자체가 바뀌는" 구조

2. **6개 언어 x 10종 CLI 도구 asyncio 병렬 통합**
   - Python(Pylint/Radon/Bandit), JS/TS(ESLint/npm-audit), C#(Roslyn), HTML(HTMLHint), CSS(Stylelint), 공통(Semgrep)
   - `asyncio.gather + asyncio.to_thread`: 동기 subprocess를 스레드풀에 오프로드하여 진정한 병렬 실행
   - 언어별 30초 타임아웃 + `return_exceptions=True`로 한 도구 실패가 전체를 중단하지 않도록 에러 격리

3. **LLM 비용 최적화 — 심각도별 모델 라우팅**
   - Critical → `claude-sonnet-4-6` (정확도 우선, 보안 이슈는 오판 불허)
   - Major → `claude-haiku-4-5` (빠르고 저렴, 리팩토링 수준은 haiku로 충분)
   - Minor → LLM 생략 (CLI 도구 판단 신뢰, 불필요한 API 호출 제거)

4. **RAG 파이프라인 — pgVector 유사 사례 검색**
   - 이슈 메시지를 임베딩 → pgVector 코사인 유사도 검색 (threshold 0.7, top-k 3)
   - 과거 유사 이슈를 LLM 프롬프트에 context로 주입 → 판단 정확도 향상
   - Mock 임베딩(해시 기반 결정적 벡터)으로 DB 없이도 테스트 재현성 확보

5. **OLTP + OLAP 이중 적재 + 장애 차등 처리**
   - PostgreSQL: 운영 조회용 (scan_executions → scan_issues → scan_summaries 3테이블)
   - BigQuery: analytics DW용 (에이전트 정확도 추이, 개발자별 패턴 집계)
   - PostgreSQL 실패 → 파이프라인 중단 (핵심 기능) / BigQuery 실패 → 로그 후 스킵 (부가 기능)

---

## Page 3 — 결과 + 시행착오 + 역량

### 정량 결과
| 항목 | 수치 |
|------|------|
| LangGraph 노드 | 8개 노드 + 2개 조건부 분기 라우터 |
| 지원 언어 | 6개 (Python/JS/TS/C#/HTML/CSS) |
| 통합 CLI 도구 | 10종 (Pylint/Radon/Bandit/ESLint/npm-audit/Roslyn/HTMLHint/Stylelint/Semgrep/pip-audit) |
| 단위 테스트 | 30+ 케이스 (Mock 기반, DB/LLM 없이 통과) |
| LLM 비용 절감 | Minor 이슈 LLM 생략 + Major→Haiku 라우팅으로 호출 비용 최소화 |
| API 엔드포인트 | 4개 (POST /scan, GET /insights/*, PATCH /issues/*, GET /health) |

### 정성 결과
- 팀 공통 Output Contract JSON 계약 기반 → 에이전트 간 안전한 데이터 전달 구조 확립
- `USE_MOCK_LLM` 환경변수 하나로 Mock/실제 전환 → 6인 병렬 독립 개발 + Week 5 통합 시 코드 충돌 최소화
- HITL 에스컬레이션 기준 수립: Critical ≥ 1 → 즉시 시니어 Slack 알림 (자동 머지 없음)
- Pydantic 경계 검증으로 내부 필드(llm_judged, _source 등)가 외부 에이전트에 노출되지 않도록 차단

### 시행착오와 해결
| 문제 | 원인 | 해결 |
|------|------|------|
| 6인 병렬 개발 시 서로의 코드 없이 어떻게 개발? | 에이전트 간 의존성 | Output Contract 계약 + Mock 서버 기반 독립 개발 구조 설계 |
| asyncio.gather에서 한 도구 실패 시 전체 중단 | 에러 전파 | `return_exceptions=True` + 언어별 타임아웃으로 에러 격리 |
| LLM 응답이 가끔 잘못된 JSON 반환 | 비결정적 LLM 출력 | 1회 재시도 + severity 허용값 검증 + 실패 시 원래 severity fallback |
| asyncpg 미설치 환경에서 import 에러 | 개발 환경 차이 | lazy import 패턴으로 Mock 모드에서는 DB 드라이버 불필요하게 설계 |

### AX/DX 역량 연결
- **업무 자동화 설계**: 수동 코드 리뷰 → AI 에이전트 기반 자동 분석·판단·알림 End-to-End 파이프라인
- **AI Native Agentic Workflow**: 단순 도구 실행이 아닌, LLM 판단 결과로 워크플로우 자체가 동적 분기
- **데이터 기반 의사결정**: RAG로 과거 사례 참조 판단, OLAP(BigQuery)로 정확도 추이 분석 기반 마련
- **비용 최적화 사고**: 모델 라우팅(Sonnet/Haiku/생략)으로 품질은 유지하면서 LLM 비용 최소화
- **운영 안정성 설계**: 타임아웃, 에러 격리, 장애 차등 처리, HITL 에스컬레이션 등 실제 서비스 수준의 설계

> **면접 어필 한 줄**: "CLI 도구의 결과를 LLM이 재판단하고, 그 판단에 따라 워크플로우가 동적으로 분기되는 AI Native 자동화 파이프라인을 LangGraph로 설계·구현하여, 코드 리뷰의 일관성 확보와 보안 이슈 즉시 대응 체계를 구축했습니다."

---

---

# 자기소개서용 문장 (700자 내외)

신입 개발자의 PR 코드 리뷰가 시니어에게 집중되어 리뷰 병목이 발생하고, 보안 취약점이 수동 리뷰에서 누락되는 문제를 해결하기 위해 AI 기반 자동 코드 리뷰 에이전트를 구축했습니다. 6인 팀에서 정적 분석·보안 스캔 에이전트 전체를 담당하며, LangGraph StateGraph로 8개 노드와 2개 조건부 분기를 가진 Agentic Workflow를 설계·구현했습니다. Python·JavaScript 등 6개 언어의 10종 CLI 도구를 asyncio로 병렬 실행하고, pgVector RAG로 과거 유사 이슈를 검색하여 Claude LLM의 심각도 판단 context로 주입했습니다. LLM 비용 최적화를 위해 Critical은 Sonnet, Major는 Haiku, Minor는 LLM 생략하는 모델 라우팅을 적용했고, Critical 이슈 발견 시 GitHub 코멘트와 Slack을 통해 시니어에게 즉시 에스컬레이션되는 HITL 체계를 구현했습니다. 그 결과, 수동 리뷰에 의존하던 코드 품질 검증을 AI가 일관된 기준으로 자동 수행하고, 보안 이슈에 즉각 대응할 수 있는 파이프라인을 완성했습니다. 이 경험을 통해 "어디까지 자동화하고 어디서 사람이 개입해야 하는가"의 경계를 설계하는 역량을 키웠으며, 이는 AX/DX 직무에서 업무 프로세스를 AI로 혁신하는 데 직접 기여할 수 있는 역량이라 확신합니다.

---

# 면접 답변용 60초 버전

"신입 개발자의 코드 리뷰가 시니어에게 집중되고 보안 이슈가 누락되는 문제를 해결하기 위해, AI 기반 자동 코드 리뷰 에이전트를 구축했습니다. 6인 팀에서 정적 분석과 보안 스캔 에이전트 전체를 담당했고, 제가 직접 한 일은 크게 세 가지입니다. 첫째, LangGraph로 8개 노드의 파이프라인을 설계하고, LLM 판단 결과에 따라 실행 경로가 동적으로 바뀌는 조건부 분기를 구현했습니다. 둘째, 6개 프로그래밍 언어의 10종 분석 도구를 asyncio 병렬 실행으로 통합하고, pgVector로 과거 유사 사례를 검색해 LLM 판단의 정확도를 높였습니다. 셋째, Critical 보안 이슈 발견 시 GitHub 코멘트와 Slack으로 시니어에게 즉시 알리는 에스컬레이션 체계를 만들었습니다. 이 프로젝트에서 배운 핵심은, 자동화 시스템에서 AI 판단과 사람의 의사결정 경계를 어떻게 설계하느냐가 시스템의 신뢰성을 결정한다는 것입니다. 이 경험을 AX/DX 직무에서 업무 프로세스 자동화에 바로 적용할 수 있습니다."
