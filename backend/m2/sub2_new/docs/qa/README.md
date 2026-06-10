# Q&A 기록 인덱스

> 대상: 비전공자 / IT 초보자
> 목적: 개발 중 헷갈렸던 개념을 나중에 다시 찾아볼 수 있도록 정리

---

## 📁 Q&A 파일 목록

| 날짜 | 파일 | 주요 내용 |
|------|------|-----------|
| 2026-05-24 | [2026-05-24.md](2026-05-24.md) | Task 6 — FastAPI 엔드포인트, Mock 테스트, Lazy import |

---

## 🗂️ Task별 핵심 Q&A 인덱스

### Task 1~3 — 분석 노드 구현 (run_tools / vector_search / llm_judge)

| 핵심 개념 | 한 줄 요약 | 상세 파일 |
|-----------|-----------|-----------|
| **subprocess** | 파이썬에서 외부 프로그램(Pylint, Bandit 등) 실행하는 방법 | [learning/python/subprocess.md](../learning/python/subprocess.md) |
| **정적 분석 도구** | Pylint(코드 품질), Bandit(보안), Semgrep(패턴 탐지), radon(복잡도), pip-audit(CVE) | [learning/security/static_analysis.md](../learning/security/static_analysis.md) |
| **asyncio.gather** | 여러 비동기 작업을 동시에 실행 (병렬처리) | [learning/python/asyncio_gather.md](../learning/python/asyncio_gather.md) |
| **Vector DB / 임베딩** | 텍스트를 숫자 배열로 변환해서 "비슷한 내용" 검색 | [learning/vector/vectordb.md](../learning/vector/vectordb.md) |
| **pgVector RAG** | PostgreSQL에서 유사도 검색으로 관련 문서 찾기 | [learning/ai/pgvector_rag.md](../learning/ai/pgvector_rag.md) |
| **프롬프트 엔지니어링** | LLM에게 명확하게 지시하는 방법 (Few-shot, CoT) | [learning/ai/prompt_engineering.md](../learning/ai/prompt_engineering.md) |
| **LLM Judge 패턴** | AI가 코드 이슈를 Critical/Major/Minor로 판단하는 구조 | [learning/ai/llm_judge_patterns.md](../learning/ai/llm_judge_patterns.md) |

**자주 헷갈리는 것:**
- Q. Pylint와 Bandit의 차이? → Pylint = 코드 스타일, Bandit = 보안 취약점
- Q. subprocess vs asyncio? → subprocess = 외부 프로그램 실행, asyncio = 파이썬 내부 비동기

---

### Task 4 — store 노드 (DB 저장)

| 핵심 개념 | 한 줄 요약 | 상세 파일 |
|-----------|-----------|-----------|
| **UPSERT** | INSERT인데 이미 있으면 UPDATE (중복 없이 저장) | [learning/database/upsert.md](../learning/database/upsert.md) |
| **PostgreSQL 인덱스** | 자주 검색하는 컬럼에 색인 걸어서 속도 높이기 | [learning/database/pg_indexes.md](../learning/database/pg_indexes.md) |
| **store 노드 패턴** | LangGraph에서 최종 결과를 DB에 저장하는 구조 | [learning/ai/store_node_patterns.md](../learning/ai/store_node_patterns.md) |
| **LangSmith 연동** | 에이전트 실행 기록을 추적/관찰하는 도구 | [learning/ai/langsmith_evaluation.md](../learning/ai/langsmith_evaluation.md) |

**자주 헷갈리는 것:**
- Q. `ON CONFLICT DO UPDATE`가 뭐야? → UPSERT. 중복 key면 UPDATE 실행
- Q. 왜 `await s.commit()`이 필요해? → commit 없으면 DB에 실제로 저장 안 됨

---

### Task 5 — LangGraph StateGraph 조립 (graph.py)

| 핵심 개념 | 한 줄 요약 | 상세 파일 |
|-----------|-----------|-----------|
| **MAS (멀티 에이전트)** | 여러 AI 에이전트가 역할 분담해서 협력하는 구조 | [learning/agent/mas.md](../learning/agent/mas.md) |
| **LangGraph StateGraph** | 노드(함수)를 연결해서 파이프라인을 만드는 도구 | [learning/agent/langgraph.md](../learning/agent/langgraph.md) |
| **LangGraph 파이프라인** | 5단계 흐름: run_tools → vector_search → llm_judge → escalate? → store | [learning/ai/langgraph_stategraph_pipeline.md](../learning/ai/langgraph_stategraph_pipeline.md) |
| **asyncio parallel** | 정적분석+보안스캔을 동시에 실행 (asyncio.gather) | [learning/ai/asyncio_parallel.md](../learning/ai/asyncio_parallel.md) |
| **다국어 라우터** | Python/JS/Java 파일에 따라 다른 분석 도구 실행 | [learning/ai/multilang_router.md](../learning/ai/multilang_router.md) |

**자주 헷갈리는 것:**
- Q. StateGraph의 `state`가 뭐야? → 모든 노드가 공유하는 데이터 저장소 (딕셔너리)
- Q. `add_node` vs `add_edge` 차이? → add_node = 기능 등록, add_edge = 실행 순서 연결
- Q. `conditional_edges`가 뭐야? → 조건에 따라 다른 노드로 분기 (if-else 같은 것)

---

### Task 6 — FastAPI 엔드포인트

> **상세 Q&A**: [2026-05-24.md](2026-05-24.md) — Q1~Q10

| # | 질문 | 핵심 답변 |
|---|------|-----------|
| Q1 | 학습 문서 어디있어? | `docs/learning/` 폴더 |
| Q2 | 200 vs 202 차이? | 200=완료, 202=접수됨(처리 중) |
| Q3 | BackgroundTasks가 뭐야? | 응답 먼저 보내고 뒤에서 LLM 실행 |
| Q4 | APIRouter 왜 써? | 파일 분리로 병렬 개발 충돌 방지 |
| Q5 | PATCH vs PUT vs DELETE? | PATCH=일부 수정, PUT=전체 교체, DELETE=삭제 |
| Q6 | Lazy import가 뭐야? | 함수 내부 import → 미설치 환경에서도 import 가능 |
| Q7 | Mock 테스트가 뭐야? | 실제 DB 대신 가짜 객체 사용 |
| Q8 | 어느 모듈을 patch해야 해? | lazy import면 원본 모듈, 일반 import면 사용처 |
| Q9 | ASGITransport가 뭐야? | 실제 서버 없이 FastAPI 앱 테스트 |
| Q10 | 오늘 어디까지 만들었어? | Task 6 완료, Task 7~8 내일 |

---

## 📚 연관 문서

- **전체 학습 개념 인덱스**: [`docs/learning/README.md`](../learning/README.md)
- **비전공자용 구현 가이드**: [`docs/learning/dev2_구현가이드_비전공자용.md`](../learning/dev2_구현가이드_비전공자용.md)
- **구현 계획**: [`docs/plans/2026-05-22-dev2-implementation-plan.md`](../plans/2026-05-22-dev2-implementation-plan.md)

---

## 🔖 복습 순서 (전체)

```
Task 1~2: subprocess → 정적 분석 도구 → asyncio.gather → 멀티 언어 라우터
Task 3:   Vector DB → pgVector RAG → 프롬프트 엔지니어링 → LLM Judge 패턴
Task 4:   UPSERT → PostgreSQL 인덱스 → store 노드 → LangSmith
Task 5:   MAS → LangGraph StateGraph → 파이프라인 조립 → 병렬 실행
Task 6:   APIRouter → 202/BackgroundTasks → HTTP 동사 → AsyncSession → Lazy import → Mock 테스트
Task 7~8: Airflow DAG → n8n 워크플로우 → E2E 테스트 (내일)
```
