# AX/DX 포트폴리오 — Dev2: AI 기반 코드 정적분석·보안스캔 자동화 에이전트

---

## 01 프로젝트 소개

- **프로젝트 이름:** Dev2 — AI 정적분석·보안스캔 에이전트  
  *(조직 지식관리 + 개발자 온보딩 멀티에이전트 플랫폼의 핵심 서브시스템)*
- **한 줄 소개:** PR이 올라오는 순간, AI가 코드 품질·보안 취약점을 자동 탐지하고 심각도를 판단해 즉시 개발팀에 전달하는 자동화 파이프라인
- **참여 인원 / 기간:** 팀 프로젝트 (멀티에이전트 플랫폼) / 2026년 5월 기준 진행 중
- **내 역할:** Dev2 서브에이전트 설계 및 구현 전담  
  — LangGraph StateGraph 설계, CLI 도구 병렬 실행 파이프라인, RAG 기반 LLM 판단 노드, 이중 DB 적재, FastAPI 엔드포인트
- **사용 기술:**  
  Python 3.11+, LangGraph, Anthropic Claude Sonnet 4.6 / Haiku 4.5,  
  pgVector(PostgreSQL), BigQuery, FastAPI, Airflow, Docker Compose,  
  LangSmith, Pylint · Bandit · ESLint · Semgrep

---

## 02 프로젝트 개요 | 배경과 목적

### 왜 시작되었는가

기존 개발팀의 코드 리뷰 프로세스는 전적으로 시니어 개발자의 수작업에 의존하고 있었다.  
PR이 열리면 개발자가 직접 코드를 읽고, 품질 문제와 보안 취약점을 눈으로 찾아야 했다.  
이 과정은 리뷰어의 숙련도에 따라 결과가 달라지고, 리뷰 대기 시간이 길어질수록 개발 속도 전체가 병목에 걸렸다.

### 어떤 문제를 해결하려 했는가

- 정적 분석 도구(Pylint, Bandit 등)는 존재하지만 **언어마다 다른 도구를 수동으로 실행**해야 했고 결과 취합·해석도 사람이 했다
- CLI 도구가 뱉는 raw 결과는 **심각도 맥락이 없어** Critical과 Minor를 같은 무게로 처리하는 문제가 있었다
- 반복적으로 나타나는 동일 유형 이슈도 **매번 새로 판단**해야 했다 — 조직 누적 지식이 재활용되지 않았다
- Critical 보안 이슈 발생 시 **자동 에스컬레이션 체계가 없어** 담당자 전달이 늦었다

### AX/DX 관점에서 무엇을 개선하려 했는가

수작업 코드 리뷰를 **AI 에이전트 파이프라인**으로 대체:

1. 언어 감지 → 도구 선택 → 실행 → 판단 → 저장까지 **전 과정 자동화**
2. LLM 기반 심각도 재판단으로 **리뷰 품질 표준화**
3. 과거 이슈 누적 데이터를 RAG로 재활용해 **조직 학습 자산화**
4. BigQuery 기반 **품질 트렌드 분석 데이터 확보**

---

## 03 진행한 일 | 배경-문제-해결

| 항목 | 내용 |
|------|------|
| **문제 상황** | PR마다 수동으로 정적분석·보안스캔 실행. 언어·팀·도구별로 파편화, CLI 결과물은 심각도 맥락 없음. Critical 취약점 묻히는 사례 발생. |
| **핵심 원인** | ① 도구 자동화 부재 ② 판단 기준 비표준화 (개인 역량 의존) ③ 지식 단절 (과거 이슈 재활용 불가) ④ 알림 자동화 부재 |
| **해결 방향** | LangGraph 기반 5-노드 파이프라인으로 도구실행→RAG검색→LLM판단→조건부분기→DB저장 완전 자동화 |
| **접근 방식** | CLI(속도·안정성) + LLM(맥락·지능) + RAG(조직 누적 지식) 3-레이어 하이브리드 설계. severity별 모델 라우팅으로 비용 통제. |

---

## 04 과정 | 나의 직접적인 액션 + 인사이트

### 내가 직접 한 일

**① LangGraph StateGraph 5-노드 파이프라인 설계·구현**
- `run_tools → vector_search → llm_judge → escalate(조건부) → store` 흐름을 StateGraph로 구현
- `_route_after_judge()` 조건부 엣지로 Critical 이슈 발생 시 자동 에스컬레이션 분기
- `PRReviewState` 팀 공통 인터페이스 상속으로 멀티에이전트 통합 호환성 확보

**② 다국어 자동 감지·도구 병렬 실행 (`run_tools.py`)**
- PR diff에서 파일 확장자 추출 → 언어별 도구 자동 선택 (Python: Pylint·Radon·Bandit / JS: ESLint·Semgrep / 공통: Semgrep OWASP)
- `asyncio.gather`로 도구 병렬 실행 (30초 타임아웃으로 파이프라인 hang 방지)
- *시행착오:* 초기에 언어 감지 로직이 노드별로 분산 → `tools/router.py` 독립 모듈화로 단일 책임 원칙 적용

**③ pgVector 기반 RAG Retrieve 구현 (`vector_search.py`)**
- 이슈 메시지 임베딩 → pgVector 코사인 유사도 검색 (threshold 0.7, 최대 3건)
- `asyncio.gather(return_exceptions=True)`로 이슈별 병렬 검색
- DB 오류 시 빈 리스트 반환 — 파이프라인 중단 없는 resilient 설계
- *시행착오:* 직렬 검색 → DB 왕복 지연이 이슈 수에 비례하여 증가 → asyncio.gather 병렬화로 해결

**④ LLM 프롬프트 엔지니어링 + 모델 라우팅 (`llm_judge.py`)**
- Few-shot 3개 + Chain-of-Thought 5단계 + RAG context 주입 + Structured Output(JSON 강제) 결합
- 모델 라우팅: Critical → Sonnet 4.6, Major → Haiku 4.5, Minor → **LLM 호출 스킵** ($0)
- JSON 파싱 실패 시 1회 재시도 (최대 2회 호출)
- `USE_MOCK_LLM` 환경변수로 실제 API 없이 개발·테스트 전환
- *시행착오:* 초기 프롬프트에서 LLM 비일관 JSON 반환 → Structured Output + Few-shot 결합으로 파싱 실패율 대폭 감소

**⑤ PostgreSQL + BigQuery 이중 적재 + Airflow 자동화 (`store.py`, DAG)**
- PostgreSQL (실시간 추적: scan_executions·scan_issues·scan_summaries)
- BigQuery (분석 DW: scan_issues_daily, PARTITION BY scan_date)
- `asyncio.gather`로 병렬 적재
- Airflow 일별 ETL DAG + 주간 오탐률·룰셋 리포트 자동 집계

### 핵심 인사이트

> CLI 도구의 결과를 그대로 LLM에 던지면 비용과 품질 모두 비효율적이다.  
> 1차 필터링(CLI) → 2차 판단(LLM) → 지식 재활용(RAG)의 레이어를 나누는 것이  
> 실무 AI 파이프라인의 핵심 설계 원칙임을 체득했다.

---

## 05 결과물 | 최종 진행 내용

### 시스템 구조

```
GitHub PR 제출
    ↓
[Dev1] Webhook 수신 → TaskPayload 생성
    ↓
[Dev2] FastAPI POST /scan (202 Accepted, 비동기)
    ↓
LangGraph StateGraph
  ├─ [run_tools]     언어 감지 → CLI 도구 병렬 실행
  ├─ [vector_search] pgVector 유사 이슈 검색 (RAG Retrieve)
  ├─ [llm_judge]     Claude severity 재판단 (RAG Generate)
  ├─ [escalate]      Critical ≥ 1 → 에스컬레이션 분기
  └─ [store]         PostgreSQL + BigQuery 이중 적재
    ↓
[Dev4] 결과 수신 + 알림
```

### 핵심 기능

| 기능 | 설명 |
|------|------|
| 다국어 자동 분석 | Python·JS·C#·HTML·CSS PR diff → 언어별 도구 자동 선택·병렬 실행 |
| RAG 기반 맥락 판단 | 과거 유사 이슈(pgVector) 자동 검색 → LLM 프롬프트에 컨텍스트 주입 |
| 모델 라우팅 | Critical→Sonnet, Major→Haiku, Minor→LLM 스킵 (비용 최적화) |
| Agentic 에스컬레이션 | Critical ≥ 1건 → 조건부 분기 → 즉시 알림 자동화 |
| 이중 적재 | PostgreSQL(실시간 추적) + BigQuery(분석 DW) 병렬 적재 |
| 자동 집계 | Airflow 일별 ETL + 주간 오탐률·룰셋 리포트 자동 생성 |

### 성과

**정량 성과**
- `asyncio.gather` 병렬화로 다언어 PR 분석 시 도구 실행 시간 단축 (직렬 대비 언어 수에 비례)
- Minor 이슈 LLM 스킵으로 해당 구간 **API 비용 $0** 실현 (모델 라우팅)
- pgVector 유사도 임계값 0.7 적용 → 오탐 방지 기반 마련

**정성 성과**
- 수작업 코드 리뷰 의존도 → **자동화 파이프라인 기반 표준화** 달성
- 개인 역량 의존 심각도 판단 → **시스템 기반 일관된 기준 수립**
- 산발된 이슈 데이터 → **재활용 가능한 RAG 지식 자산**으로 전환
- BigQuery 이중 구조로 **팀 코드 품질 트렌드 측정 기반** 구축
- LangSmith 기반 **재현 가능한 AI 파이프라인 품질 측정 체계** 수립

---

## 06 성장한 점

### 기술적 성장
- **LLM 파이프라인 설계:** CLI·RAG·LLM을 레이어드하게 결합하는 실무 AI 시스템 설계 방법 체득
- **비용 인식 엔지니어링:** 모델 라우팅 + Minor 스킵으로 기능 저하 없이 LLM 비용 통제하는 실제 LLMOps 패턴 구현
- **비동기 병렬 처리:** asyncio.gather + return_exceptions=True로 부분 실패가 전체 파이프라인 중단 없는 resilient 설계

### 문제 해결 방식
- "LLM 하나로 다 해결" → **도구 적합성에 따라 레이어 분리**하는 사고방식 확립
- 에러 처리를 "예외 방지"가 아니라 **"파이프라인 지속성 보장"** 관점으로 설계

### 협업 방식
- 팀 공통 `PRReviewState` 인터페이스 상속으로 **계약 기반 멀티에이전트 협업 구조** 경험

### 비즈니스 이해
- 보안 이슈 자동 탐지·에스컬레이션 = 단순 개발 도구가 아닌 **리스크 관리 자동화**
- BigQuery 장기 누적 → 개발팀 생산성 지표와 기술 부채 트렌드를 **데이터 기반으로 측정**하는 DX 관점 이해

---

## 07 나의 역량 | 입사 시 기여할 수 있는 부분

### 역량 요약

| 역량 | 근거 |
|------|------|
| AI 파이프라인 설계·구현 | LangGraph 5-노드 StateGraph, RAG 패턴 직접 구현 |
| LLM 비용 최적화 | 모델 라우팅, Minor 스킵, Mock LLM 환경 분리 |
| 데이터 파이프라인 자동화 | PostgreSQL+BigQuery 이중 적재, Airflow ETL DAG |
| 비동기 병렬 처리 | asyncio.gather 기반 resilient 파이프라인 |
| API 설계 | FastAPI 202 Accepted 비동기 패턴, Pydantic 계약 기반 설계 |
| LLMOps | LangSmith 자동 추적, Mock LLM 테스트 환경 분리 |

### AX/DX 직무 연결 강점

- **업무 자동화:** 수작업 코드 리뷰 → AI 파이프라인 대체 (AX 전형적 사례 직접 설계·구현)
- **데이터 기반 의사결정:** 산발된 결과 → BigQuery 구조화 → 품질 트렌드 측정 가능하게 만든 DX 경험
- **비용 인식 AI 적용:** LLM 도입을 넘어 "어디에 얼마만큼 써야 하는지" 설계한 실무적 AI 활용 역량

### 면접 어필 한 줄

> "저는 AI를 도입하는 것이 아니라,  
> 기존 업무 흐름의 어느 지점에 AI가 들어가야 효과적인지를 설계하는 경험을 했습니다."

---

## 자기소개서용 문장 (700자)

저는 반복적인 수작업 업무를 AI 자동화 파이프라인으로 전환하는 프로젝트를 직접 설계하고 구현한 경험이 있습니다.

개발팀에서 GitHub PR이 올라올 때마다 시니어 개발자가 수동으로 정적 분석 도구를 실행하고 보안 취약점을 찾아야 했습니다. 언어마다 다른 도구를 직접 골라 실행해야 했고, 도구가 뱉는 raw 결과에는 심각도 맥락이 없어 Critical 이슈가 묻히는 경우도 발생했습니다. 또한 과거 유사 이슈가 의사결정에 재활용되지 않아 조직 학습이 단절되는 비효율이 있었습니다.

저는 이 문제를 해결하기 위해 LangGraph 기반 5-노드 AI 에이전트 파이프라인을 설계했습니다. PR 제출 즉시 파일 언어를 자동 감지해서 Pylint·Bandit·ESLint 같은 도구들을 병렬로 실행하고, 과거 유사 이슈를 pgVector RAG로 자동 검색해서 Claude에 컨텍스트로 주입한 뒤 심각도를 재판단하는 구조입니다. Critical 이슈 발생 시에는 조건부 분기를 통해 담당팀에 즉시 에스컬레이션됩니다. 분석 결과는 PostgreSQL과 BigQuery에 이중 적재되어 실시간 추적과 장기 품질 트렌드 분석이 동시에 가능합니다. LLM 비용 통제를 위해 심각도별 모델 라우팅을 직접 설계해 Minor 이슈에는 API 호출 자체를 제거했습니다.

그 결과 수작업에 의존하던 코드 리뷰가 표준화된 자동화 파이프라인으로 전환되었고, 산발된 이슈 데이터가 재활용 가능한 조직 지식 자산으로 구조화됐습니다. AX/DX 직무에서 업무 자동화와 데이터 기반 의사결정 환경을 만드는 일에 이 경험을 바로 연결할 수 있다고 생각합니다.

---

## 면접 답변 (60초)

"저는 개발팀의 코드 리뷰 수작업을 AI 에이전트 파이프라인으로 자동화한 프로젝트를 담당했습니다.

기존에는 PR이 올라오면 개발자가 직접 정적 분석 도구를 실행하고 보안 취약점을 눈으로 찾아야 했는데, 언어마다 도구가 달라서 파편화되어 있었고, 심각도 맥락 없는 raw 결과를 사람이 직접 해석해야 하는 비효율이 있었습니다.

저는 LangGraph로 5단계 파이프라인을 직접 설계했습니다. PR이 들어오면 파일 언어를 자동 감지해서 Pylint·Bandit·ESLint 같은 도구들을 병렬로 실행하고, 과거 유사 이슈를 pgVector로 자동 검색해서 Claude에 컨텍스트로 줬습니다. Critical 이슈가 있으면 자동으로 에스컬레이션되고, 결과는 PostgreSQL과 BigQuery에 이중 저장해서 장기 품질 트렌드 분석도 가능하게 했습니다.

LLM 비용도 직접 설계했는데, 심각도가 낮은 이슈는 LLM 호출 자체를 스킵하는 모델 라우팅을 적용했습니다.

이 경험을 통해 업무 자동화는 AI를 도입하는 것보다, 기존 흐름의 어느 지점에 AI를 넣어야 효과적인지를 설계하는 게 핵심이라는 걸 직접 체득했습니다."
