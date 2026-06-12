# /study — 역공부 커맨드

AI가 짜준 코드, 또는 이해가 부족한 코드를 **내 것으로 만드는** 대화형 학습 세션.

**사용법**:
```
/study                              → 이 프로젝트에서 공부할 파일 목록 보여줌
/study dev2/tools/python/pylint_tool.py  → 특정 파일 역공부 시작
/study interview                    → 전체 프로젝트 면접 질문 모드
/study quiz                         → 오늘 공부한 내용 퀴즈
```

---

## 세션 진행 방식

### 모드 1: 파일 역공부 (`/study [파일경로]`)

파일을 지정하면 아래 순서로 진행한다:

**Step 1 — 소크라테스 모드 (설명 먼저 안 함)**

```
나: 이 파일에서 [함수/변수]를 봤어요. 어떤 역할을 하는 것 같나요?
사용자: [추측/설명 시도]
나: 맞아요 / 거기서 한 발 더 가면 — [빈 부분만 채워줌]
```

→ 내가 설명을 먼저 쏟아내지 않는다. 사용자가 말한 뒤 빠진 부분만 채운다.

**Step 2 — 핵심 질문 3개**

파일당 "이것만 알면 면접에서 설명 가능한" 질문 3개를 제시한다:

```markdown
이 파일의 핵심 질문:
1. [개념 이해] 이 함수는 왜 존재하나요? 없으면 어떻게 되나요?
2. [설계 이유] 왜 이렇게 만들었나요? 다른 방법도 있었을 텐데요.
3. [실무 연결] 실제 서비스에서 이 코드가 잘못되면 어떤 문제가 생기나요?
```

사용자가 대답하면 피드백. 대답 못 해도 힌트 주고 다시 시도.

**Step 3 — 백지 재작성 챌린지**

```
이제 파일을 닫고 핵심 로직을 빈 종이에 써보세요.
완벽하지 않아도 됩니다. 기억나는 것만.

다 쓰셨으면 알려주세요. 원본과 비교해드릴게요.
```

→ 사용자가 "다 썼어" 하면 원본에서 다른 부분만 짚어준다.

**Step 4 — 면접 한 줄 답변 완성**

```
면접관이 "이 코드 설명해주세요" 라고 하면
한 문장으로 뭐라고 하시겠어요?

사용자 답변 → 다듬어서 "이렇게 말하면 더 임팩트 있어요" 피드백
```

---

### 모드 2: 파일 목록 (`/study` 단독)

이 프로젝트에서 공부할 파일을 난이도 순으로 보여준다:

```markdown
## 지금 공부하면 좋은 파일 순서 (쉬운 것 → 어려운 것)

🟢 입문 (Python 기초 + subprocess)
  1. dev2/tools/python/pylint_tool.py    — subprocess로 외부 도구 실행
  2. dev2/nodes/escalate.py              — async/await + HTTP 호출

🟡 중급 (FastAPI + SQL)
  3. dev2/api/insights.py               — FastAPI GET + SQL 파라미터 바인딩
  4. dev2/api/scan.py                   — FastAPI POST + 비동기 처리

🔴 심화 (LangGraph + LLM)
  5. dev2/graph.py                      — LangGraph StateGraph 조립
  6. dev2/nodes/llm_judge.py            — LLM 모델 라우팅 + 할루시네이션 방지

어떤 파일부터 시작할까요?
```

---

### 모드 3: 면접 준비 (`/study interview`)

전체 프로젝트에서 면접 질문 10개를 생성하고 하나씩 물어본다.

```markdown
## 이 프로젝트 면접 질문 10선

기술 나열 X — "왜 그 선택을 했는지" 중심으로 묻는다.

1. "LangGraph를 쓴 이유가 뭔가요? 그냥 함수 호출이랑 뭐가 달라요?"
2. "Critical 이슈와 Minor 이슈에 다른 LLM 모델을 쓴 이유는요?"
3. "SQL 쿼리를 f-string으로 안 쓰고 파라미터 바인딩을 쓴 이유가요?"
4. "Slack 알림이 실패해도 파이프라인을 계속 진행한 이유는요?"
5. "asyncio.gather에서 return_exceptions=True를 쓴 이유는요?"
...

준비됐으면 "시작" 이라고 말해주세요.
한 문제씩 물어볼게요. 답하면 피드백 드립니다.
```

---

### 모드 4: 퀴즈 (`/study quiz`)

최근 공부한 파일 기반으로 4지선다 퀴즈 3문제 출제.

```markdown
## 퀴즈 (3문제)

Q1. Pylint의 메시지 타입 "E"는 어떤 severity로 매핑되나요?
  a) Minor
  b) Major  
  c) Critical ← 정답
  d) Info

Q2. ...
```

---

## 학습 원칙

1. **설명을 먼저 하지 않는다** — 사용자가 추측하고 틀린 뒤에 채워준다
2. **"왜"를 항상 묻는다** — "어떻게"보다 "왜 이렇게 설계했는지"가 면접에서 중요
3. **한 파일에 30분** — 한 번에 너무 많이 하면 기억에 안 남음
4. **틀려도 괜찮다** — 틀린 뒤에 기억하는 게 처음부터 맞는 것보다 오래 감
5. **내 말로 정리가 끝** — 마지막엔 반드시 "한 줄 요약" 사용자가 직접 쓰게 함

---

## 학습 방법론: 부수고 고치기 (Break & Fix)

> **핵심 철학**: 코드를 외우면 잊어버린다. 왜 그 코드가 있는지 알면 절대 안 잊는다.
> 연습 폴더 따로 만들 필요 없다. **이미 구현된 코드가 곧 실습장이다.**

---

### 왜 "부수고 고치기"인가?

책 읽어서 수영 배울 수 없다. 직접 물에 들어가야 한다.

코드도 마찬가지:
- 읽기만 하면 → "아 그렇구나" 하고 넘어감 → 3일 뒤 기억 0
- 직접 지우고 실행하면 → 에러 보고 → "아 이게 있어야 하는 이유가 이거구나" → 기억에 박힘

---

### 6단계 사이클 (파일 1개당 약 36분)

```
① Read      (10분) — 파일 전체를 한 번 읽는다. 이해 안 돼도 OK.
② Predict   ( 5분) — "이 코드를 지우면 어떻게 될까?" 예측을 말로 해본다.
③ Delete    ( 5분) — 예측한 부분을 실제로 지운다 (또는 값을 바꾼다).
④ Run       ( 5분) — 테스트 또는 import를 실행한다. 어떤 에러가 나는가?
⑤ Understand(10분) — 에러 메시지를 읽는다. "왜 이 에러가 났지?" 를 말로 설명해본다.
⑥ Restore   ( 1분) — git restore [파일명] 으로 원상복구. 다음 파트로.
```

**git restore가 안전망이다.** 무서워하지 않아도 된다. 언제든 되돌릴 수 있다.

---

### 파일별 부수는 방법 (구체적 실습 가이드)

#### 🟢 `dev2/tools/python/pylint_tool.py` — 입문 (30분)

```python
# 실습 1: 빈 리스트 가드 제거
# 지울 부분:
if not files:
    return []

# 예측: 어떻게 될까?
# → Pylint에 빈 파일 목록을 넘기면?
# → subprocess가 "python -m pylint" 만 실행하면?

# 실습 2: 타임아웃 0으로 변경
timeout=30  →  timeout=0

# 예측: 어떻게 될까?
# → subprocess.TimeoutExpired 에러?
# → 왜 타임아웃이 필요한가?

# 실습 3: SEVERITY_MAP에서 "E" 키 제거
SEVERITY_MAP = {
    # "E": "Critical",  ← 이 줄 주석처리
    "F": "Critical",
    ...
}
# 예측: E타입 이슈가 들어오면 severity가 뭐가 될까?
# → .get("E", "Minor") → "Minor" 반환됨
# → 왜 default값이 "Minor"인가?
```

#### 🟢 `dev2/nodes/escalate.py` — 입문 (30분)

```python
# 실습 1: except 블록 제거
try:
    async with httpx.AsyncClient() as client:
        await client.post(...)
except Exception:          ← 이 블록 전체 삭제
    logger.warning(...)

# 예측: Slack URL이 잘못됐을 때 어떻게 될까?
# → 에러가 파이프라인 전체를 멈춤
# → 왜 알림 실패가 파이프라인을 막으면 안 되는가?

# 실습 2: timeout 파라미터 제거
httpx.AsyncClient(timeout=10.0)  →  httpx.AsyncClient()
# 예측: Slack 서버가 응답 안 하면 어떻게 될까?
# → 무한 대기? → 파이프라인 블로킹
```

#### 🟡 `dev2/api/insights.py` — 중급 (30분)

```python
# 실습 1: 파라미터 바인딩 → f-string으로 바꾸기
# 원래:
WHERE se.developer_id = :did", {"did": developer_id}

# 바꿔보기:
WHERE se.developer_id = '{developer_id}'"  # f-string

# 예측: 코드는 동작하는가? 어떤 위험이 생기는가?
# → developer_id = "'; DROP TABLE scan_issues;--" 을 넣으면?
# → 이게 SQL 인젝션. 면접에서 실제 예시로 설명할 수 있음.

# 실습 2: try/except 제거
# 예측: DB 연결 실패 시 어떻게 될까?
# → 500 Internal Server Error 반환
# → insights 조회 실패가 서비스 전체를 막으면 안 되는 이유?
```

#### 🔴 `dev2/graph.py` — 심화 (30분)

```python
# 실습 1: conditional_edges를 일반 add_edge로 바꾸기
# 원래:
graph.add_conditional_edges("llm_judge", route_after_judge)

# 바꿔보기:
graph.add_edge("llm_judge", "store")  # escalate로 가는 경로 제거

# 예측: Critical 이슈가 나와도 에스컬레이션 안 됨
# → conditional_edges가 없으면 분기가 불가능하다는 것을 체감

# 실습 2: START 엣지 제거
graph.add_edge(START, "run_tools")  ← 삭제
# 예측: 그래프 compile()이 실패? 아니면 invoke()에서 실패?
# → START가 없으면 어디서 시작해야 하는지 LangGraph가 모름
```

---

### 엄마한테 설명 테스트 (Feynman 기법)

코드를 부수고 복구한 뒤 아래 질문에 대답해본다.
대답이 막히면 → 아직 이해한 게 아님 → 다시 실습.

```
"엄마, 내가 만든 코드에서 [기술]이 뭔지 설명해줄게."

pylint_tool.py: "엄마, subprocess가 뭔지 알아? ..."
escalate.py:    "엄마, try/except를 왜 쓰는지 알아? ..."
insights.py:    "엄마, SQL 인젝션이 뭔지 알아? ..."
graph.py:       "엄마, LangGraph가 그냥 if문이랑 다른 게 뭔지 알아? ..."
```

설명이 막히는 부분 = 아직 모르는 부분. 거기를 다시 부수고 고친다.

---

### 오늘 바로 시작하는 30분 플랜

```
0~5분:   pylint_tool.py 파일 열기 + 전체 읽기 (이해 안 돼도 OK)
5~10분:  "if not files: return [] 를 지우면?" 예측 말로 해보기
10~15분: 실제로 지우고 → python -c "from dev2.tools.python.pylint_tool import run_pylint; run_pylint([])"
15~20분: 에러 읽기 → "왜 이 에러가 났지?" 설명하기
20~25분: git restore dev2/tools/python/pylint_tool.py → 복구 확인
25~30분: 면접 한 줄 써보기: "subprocess는 _____ 때문에 timeout=30이 필요하다"
```

**한 파일씩, 하루 30분.** 6일이면 핵심 6파일 완료. 그게 면접 준비의 전부다.

---

## 파일별 핵심 면접 질문 (빠른 참조)

| 파일 | 핵심 질문 |
|------|-----------|
| `pylint_tool.py` | "subprocess 실행 시 timeout을 왜 걸었나요?" |
| `escalate.py` | "알림 실패가 파이프라인을 막으면 안 되는 이유는?" |
| `insights.py` | "SQL 인젝션을 실제로 어떻게 방어했나요?" |
| `llm_judge.py` | "LLM 응답이 잘못된 JSON일 때 어떻게 처리했나요?" |
| `graph.py` | "조건부 엣지(conditional_edges)가 단순 if문과 다른 점은?" |
| `vector_search.py` | "RAG를 쓴 이유 — LLM이 혼자 판단하면 안 되나요?" |
| `store.py` | "PostgreSQL과 BigQuery에 동시에 저장하는 이유는?" |

---

---

# 직무별 학습 트랙

## `/study track ax` — AX/DX (AI 전환) 직무

### 이 직무가 하는 일

기업의 업무 프로세스에 AI를 붙여서 자동화하거나 효율을 높이는 역할.
"AI 챗봇 도입", "문서 자동 분류", "코드 리뷰 자동화" 같은 프로젝트를 설계·구현.

---

### ✅ 이미 프로젝트에서 경험한 것 (면접에서 바로 쓸 수 있음)

| 개념 | 프로젝트 어디서? | 면접 한 줄 |
|------|----------------|-----------|
| **RAG 패턴** | `vector_search.py` → `llm_judge.py` | "LLM 단독 판단 대신 pgVector로 유사 사례를 검색해 context로 주입, 할루시네이션을 줄였습니다" |
| **LLM 모델 라우팅** | `llm_judge.py` MODEL_ROUTING | "이슈 심각도에 따라 Sonnet/Haiku를 분기해 비용 대비 정확도를 최적화했습니다" |
| **AI 에이전트 오케스트레이션** | `graph.py` StateGraph | "LangGraph로 5개 노드 파이프라인을 조립, Critical 감지 시 조건부 경로 분기를 구현했습니다" |
| **Prompt Engineering** | `prompts/severity_judge.py` | "Few-shot + Chain-of-Thought + Structured Output 3기법을 결합해 LLM 출력 신뢰도를 높였습니다" |
| **LLMOps / 관찰가능성** | LangSmith 연동 (`graph.py`) | "LangSmith로 모든 에이전트 실행을 추적, 어느 노드에서 시간이 걸리는지 파악합니다" |
| **비동기 파이프라인** | `asyncio.gather` 병렬 실행 | "분석 에이전트 2개를 asyncio.gather로 병렬 실행, 30초 타임아웃을 적용했습니다" |
| **Vector DB** | pgVector HNSW 인덱스 | "임베딩 유사도 검색으로 과거 유사 이슈를 RAG context로 활용했습니다" |

---

### ❌ 추가로 공부해야 할 AX/DX 개념

#### 우선순위 HIGH (면접 필수)

**1. LLM 평가 지표 (Evaluation Metrics)**
```
왜 필요: AI 도입 후 "이게 정말 좋아졌나?" 를 숫자로 증명해야 함
핵심 개념:
  - RAGAS: RAG 품질 자동 평가 (Faithfulness, Relevancy, Context Precision)
  - Precision / Recall: 탐지 정확도 vs 누락률
  - Hallucination Rate: LLM이 잘못된 정보를 얼마나 내뱉는지
공부 방법: 프로젝트 LangSmith 대시보드 → Golden Dataset 비교
```

**2. 프롬프트 엔지니어링 심화**
```
왜 필요: AX 직무의 핵심 스킬 — 같은 LLM도 프롬프트로 결과가 2배 달라짐
핵심 기법:
  - System Prompt vs User Prompt 분리
  - Guardrail: "모르면 '모릅니다' 라고 답하라" 명시
  - Output Schema 강제: JSON 형식 고정으로 파싱 실패 제거
  - Temperature 조절: 분류 작업 0, 창의적 작업 0.7~1.0
이미 한 것: severity_judge.py 프롬프트 (복습하면 면접 답변 완성)
```

**3. LLM 비용 최적화**
```
왜 필요: 기업 AX 프로젝트에서 비용 통제는 필수 KPI
핵심 개념:
  - 모델 라우팅: 간단한 작업 → Haiku, 복잡한 판단 → Sonnet
  - Prompt Caching: 반복되는 system prompt 캐시로 비용 70% 절감
  - Batch API: 실시간 불필요한 작업은 배치로 처리
이미 한 것: MODEL_ROUTING (Minor → LLM 생략) — 이게 비용 최적화!
```

#### 우선순위 MEDIUM (6개월 내)

**4. Fine-tuning 기초 개념** (구현 아니어도 됨, 개념만)
```
언제 씀: 특정 도메인(법률/의료/금융)에서 일반 LLM이 부족할 때
LoRA, PEFT 개념 정도만 알면 면접에서 "알고 있다"고 할 수 있음
```

**5. Multi-modal AI**
```
이미지 + 텍스트 동시 처리 (PDF 이미지 → 텍스트 추출)
프로젝트에서: UnStructured.io + Gemini Multimodal (CLAUDE.md §9)
```

---

### AX/DX 면접 실전 Q&A 10선

```
Q1: "RAG가 뭔가요? 왜 LLM에 RAG를 붙이나요?"
A: "LLM은 학습 데이터 외 정보를 모릅니다. RAG는 외부 DB에서
   관련 문서를 검색해 LLM에게 '참고자료'로 주는 방법입니다.
   저는 pgVector로 과거 유사 이슈를 검색해 LLM 판단 근거로 활용했습니다."

Q2: "할루시네이션을 어떻게 줄였나요?"
A: "3단계로 방어했습니다.
   ① RAG: 유사 과거 사례를 context로 주입해 근거 없는 판단 방지
   ② Structured Output: JSON 형식 강제로 엉뚱한 응답 차단
   ③ Validation: severity가 허용값(Critical/Major/Minor) 외면 재시도"

Q3: "LangGraph를 왜 썼나요? 그냥 함수 호출 안 되나요?"
A: "단순 파이프라인이면 함수로 충분합니다.
   LangGraph를 쓴 이유는 '조건부 분기' 때문입니다.
   Critical 이슈 유무에 따라 실행 경로가 달라지는데,
   이런 동적 분기를 StateGraph로 명시적으로 표현하면
   유지보수와 디버깅이 쉬워집니다."

Q4: "AI 도입 성과를 어떻게 측정하나요?"
A: "정량 지표로 3가지를 씁니다.
   ① 처리 시간: 수동 45분 → 자동 90초 (97% 절감)
   ② 탐지 정확도: Golden Dataset 대비 Precision/Recall
   ③ 비용: 모델 라우팅으로 Minor 이슈 LLM 생략 → API 비용 절감"

Q5: "프롬프트 엔지니어링에서 가장 중요한 게 뭔가요?"
A: "'모르면 모른다고 해라' 는 Guardrail입니다.
   LLM은 그럴듯한 답을 만들어내려는 경향이 있어서
   근거 없으면 Unknown을 반환하도록 명시적으로 지시해야
   할루시네이션을 막을 수 있습니다."
```

---

## `/study track de` — 데이터 엔지니어 직무

### 이 직무가 하는 일

데이터가 원천(DB, 로그, API)에서 분석가·ML팀이 쓸 수 있는 형태로
자동으로 흘러가는 파이프라인을 설계하고 유지한다.

---

### ✅ 이미 프로젝트에서 경험한 것

| 개념 | 프로젝트 어디서? | 면접 한 줄 |
|------|----------------|-----------|
| **PostgreSQL** | `insights.py`, `store.py` | "파라미터 바인딩으로 SQL 인젝션 방지, 집계 쿼리(GROUP BY, date_trunc) 작성 경험" |
| **BigQuery (OLAP)** | `store.py` dual write | "PostgreSQL은 운영 조회, BigQuery는 장기 분석용으로 이중 적재 파이프라인 구현" |
| **OLTP vs OLAP 설계** | `store.py` 주석 | "단건 조회 속도 vs 대용량 집계 목적에 따라 저장소를 분리하는 이유 설명 가능" |
| **비동기 Python** | `asyncio.gather`, `async/await` | "I/O 대기 없이 병렬 처리로 파이프라인 처리량을 높이는 방법 구현 경험" |
| **Airflow 개념** | `docs/learning/infra/airflow.md` | "DAG, Task, Operator 개념 학습 완료 (구현 경험 필요)" |
| **데이터 파이프라인 설계** | 전체 graph.py | "입력 → 변환 → 저장 흐름, 실패 시 fallback 처리 패턴 경험" |

---

### ❌ 추가로 공부해야 할 데이터 엔지니어 개념

#### 우선순위 HIGH (면접 필수)

**1. SQL 심화 — 윈도우 함수 + CTE**
```sql
-- 이것만 알면 DE 코딩테스트 통과
-- CTE (WITH): 복잡한 쿼리를 단계별로 쪼개기
WITH monthly_stats AS (
    SELECT developer_id, COUNT(*) as issue_count
    FROM scan_issues
    GROUP BY developer_id
)
SELECT *, RANK() OVER (ORDER BY issue_count DESC) as rank
FROM monthly_stats;

-- 윈도우 함수: 행마다 집계값 붙이기 (GROUP BY와 다름)
-- ROW_NUMBER, RANK, LEAD, LAG, SUM OVER() 꼭 익힐 것
공부 방법: 현재 insights.py SQL 쿼리에 윈도우 함수 추가해보기
```

**2. Airflow DAG 직접 구현**
```python
# 개념만 알면 안 됨 — 실제로 짜봐야 면접 통과
from airflow import DAG
from airflow.operators.python import PythonOperator

# 매일 새벽 2시에 PostgreSQL → BigQuery 적재
dag = DAG('daily_scan_to_bq', schedule_interval='0 2 * * *')

# 이 프로젝트와 연결: store.py의 BigQuery 적재를 Airflow Task로!
공부 방법: store.py의 BigQuery 적재 로직 → Airflow DAG으로 포장해보기
```

**3. 데이터 모델링 (스타 스키마)**
```
현재 프로젝트: scan_executions → scan_issues → scan_summaries (OLTP)
DE 관점으로 바꾸면:
  Fact 테이블: scan_issues (측정값: issue 발생)
  Dimension 테이블: developers, rules, files
  
왜 중요: "이 테이블 설계 왜 이렇게 했나요?" 는 DE 면접 단골 질문
```

**4. pandas 기초 + 데이터 정제**
```python
# SQL로 못 하는 복잡한 변환은 pandas로
import pandas as pd

df = pd.read_sql(query, conn)
df['severity_score'] = df['severity'].map({'Critical': 3, 'Major': 2, 'Minor': 1})
df.groupby('developer_id')['severity_score'].mean()

# 이 프로젝트와 연결: insights API 결과를 pandas로 후처리
```

#### 우선순위 MEDIUM

**5. dbt (data build tool) 개념**
```
역할: SQL 변환 로직을 버전관리 가능한 코드로 관리
비유: "SQL의 Git + 테스트"
프로젝트 연결: insights.py SQL 쿼리 → dbt model로 변환 연습
```

**6. Kafka / 스트리밍 기초 개념**
```
배치(Airflow) vs 스트리밍(Kafka) 차이 설명할 수 있어야 함
언제 씀: "PR이 올라오는 즉시" 처리 → 스트리밍
         "하루치 분석" → 배치
```

**7. Docker Compose 실행**
```
이 프로젝트에 docker-compose.yml 있음 — 직접 실행해보기
PostgreSQL + FastAPI를 도커로 띄우는 경험이 DE 실무 기본
```

---

### 데이터 엔지니어 면접 실전 Q&A 10선

```
Q1: "ETL과 ELT의 차이가 뭔가요?"
A: "ETL은 변환 후 적재(Transform → Load), ELT는 적재 후 변환(Load → Transform)입니다.
   BigQuery처럼 처리 능력이 강한 OLAP이 생기면서 ELT가 대세가 됐습니다.
   일단 원시 데이터를 다 적재하고, 필요할 때 SQL로 변환하면
   원본 데이터를 보존하고 재처리가 쉬워집니다."

Q2: "이 프로젝트에서 PostgreSQL과 BigQuery를 같이 쓴 이유는?"
A: "목적이 다릅니다.
   PostgreSQL: 운영 조회 — PR별 이슈 상세, scan_id로 빠른 단건 조회
   BigQuery: 분석 DW — 개발자별 패턴 추이, 수개월치 집계
   각 저장소의 강점에 맞는 역할을 분리해 이중 적재했습니다."

Q3: "데이터 파이프라인에서 실패 처리를 어떻게 하나요?"
A: "저는 두 가지 원칙을 적용했습니다.
   ① 핵심 경로(PostgreSQL)는 실패 시 예외를 상위로 전파해 즉시 알림
   ② 부가 경로(BigQuery, Slack)는 실패를 로그만 남기고 파이프라인 계속 진행
   알림 실패가 전체 파이프라인을 막으면 안 된다는 원칙입니다."

Q4: "SQL 윈도우 함수와 GROUP BY 차이는?"
A: "GROUP BY는 그룹당 1행으로 축약됩니다.
   윈도우 함수는 원래 행을 유지하면서 집계값을 옆에 붙여줍니다.
   '각 개발자의 이슈 건수 + 전체 대비 순위'를 동시에 보려면
   GROUP BY만으로는 불가능하고 RANK() OVER()가 필요합니다."

Q5: "배치 처리와 스트리밍 처리 언제 각각 쓰나요?"
A: "데이터의 신선도 요구사항으로 결정합니다.
   배치: '어제 하루치 통계' — Airflow로 매일 새벽 실행
   스트리밍: 'PR 올라오면 즉시 분석' — Kafka 또는 Webhook 트리거
   이 프로젝트는 GitHub Webhook → 즉시 분석이라 스트리밍에 가깝습니다."
```

---

## `/study gap` — 아직 없는 기술 채우기 (우선순위 순)

지금 당장 사이드 프로젝트나 개인 학습으로 채워야 할 것:

```markdown
## 취업 전 반드시 채울 기술 갭

### 1주 안에 (작은 실습으로)
- [ ] SQL 윈도우 함수: 현재 insights.py 쿼리에 RANK() 추가해보기
- [ ] pandas 기초: insights API 결과를 DataFrame으로 가공해보기
- [ ] Docker Compose 실행: 이 프로젝트 docker-compose.yml 직접 실행

### 2~3주 안에
- [ ] Airflow DAG 1개: store.py BigQuery 적재를 DAG Task로 만들기
- [ ] RAGAS 평가: llm_judge 결과를 RAGAS로 자동 채점해보기

### 1~2개월 안에
- [ ] dbt model 1개 작성해보기 (SQL 변환 버전관리 경험)
- [ ] Kafka 개념 학습 + 간단한 producer/consumer 실습
- [ ] 클라우드 1개: GCP BigQuery 직접 쿼리 또는 AWS S3 + Athena 기초

### 포트폴리오에 추가하면 좋은 것
- [ ] insights API → Streamlit 대시보드로 시각화 (시각적 임팩트)
- [ ] Airflow DAG → 자동 분석 파이프라인 화면 캡처
```
