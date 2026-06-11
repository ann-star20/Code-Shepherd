# Cloud SQL 적재 테스트 학습 노트

> 관련 파일: `dev2/api/scan.py`, `dev2/db.py`, `dev2/nodes/store.py`
> 작성일: 2026-06-05
> 복습 예정: D+1, D+3, D+7

---

## 한 줄 요약

Dev2 파이프라인이 발견한 보안 이슈를 Cloud SQL(PostgreSQL)에 3단계로 저장하는 흐름을 두 가지 방법으로 검증했다.

---

## 왜 했나요?

LangGraph 파이프라인이 코드를 분석해도, 그 결과가 DB에 저장되지 않으면 Dev4(평가)나 Dev5(커리큘럼)가 활용할 수 없다.  
이번 테스트의 목적: **"코드 → 분석 → DB 저장"의 전체 흐름이 실제로 동작하는지 확인.**

---

## 두 가지 테스트

### 테스트 1 — POST /scan/mock-bandit (단순 직통)

**흐름:**
```
mock_vulnerable/auth.py (위험한 코드 파일)
        ↓
Bandit 스캐너 실행 → bandit_result.json 생성
        ↓
JSON 파싱 → severity 변환
  HIGH   → Critical
  MEDIUM → Major
  LOW    → Minor
        ↓
Cloud SQL 3단계 INSERT
  1. scan_executions (실행 기록 1행)
  2. scan_issues     (이슈별 10행)
  3. scan_summaries  (요약 1행: Critical 2 / Major 3 / Minor 5)
```

**결과:** scan_id = 87, 이슈 10개 저장 완료

---

### 테스트 2 — POST /scan (LangGraph 전체 파이프라인)

**흐름:**
```
가짜 PR diff 입력 ("SELECT * FROM users WHERE id = " + user_id)
        ↓
① run_tools_node   → Pylint, Bandit으로 raw 이슈 목록 생성
        ↓
② vector_search_node (RAG)
   → 이슈 메시지를 벡터로 변환
   → pgVector에서 과거 유사 이슈 검색 → similar_issues 주입
   (USE_MOCK_LLM=true: 키워드 매칭으로 대체)
        ↓
③ llm_judge_node   → LLM이 severity 재판단 (Mock 모드)
        ↓
④ store_node       → Cloud SQL INSERT (scan_executions id=89)
        ↓
⑤ comment_generate_node → 코멘트 텍스트 생성
        ↓
⑥ github_comment_node   → GitHub PR 코멘트 등록 (Mock)
```

**결과:** scan_id = 89, user_id = junior_dev_01 UUID로 저장 완료

---

## 오늘 수정한 버그 3개

### 버그 1 — `insert_scan_execution` 파라미터 불일치
- **문제**: `scan.py`는 `developer_id`, `trace_id`를 넘기는데 `db.py`에 해당 파라미터가 없었음
- **수정**: `db.py`에 `developer_id`, `trace_id` 옵셔널 파라미터 추가 + `user_id` 컬럼에 매핑
- **파일**: `dev2/db.py`

### 버그 2 — `user_id` NOT NULL 위반
- **문제**: `scan.py` mock 엔드포인트가 `developer_id="dev2"` (문자열)를 넘겼는데 DB는 UUID 타입 + NOT NULL
- **수정**: 실제 seed UUID(`00000000-0000-0000-0000-000000000001` = junior_dev_01)로 교체
- **파일**: `dev2/api/scan.py`

### 버그 3 — `agent` CHECK 제약 위반
- **문제**: `agent="bandit"`을 INSERT했는데 DB CHECK 제약이 `bandit`을 허용하지 않음
- **허용값**: `static_analysis`, `security_scan`, `test_verification`, `performance`
- **수정**: `agent="security_scan"`으로 변경 (Bandit은 보안 스캔 도구이므로 적절)
- **파일**: `dev2/api/scan.py`

### 버그 4 — `store.py`가 `developer_id`를 DB에 안 넘김
- **문제**: `_persist()` 함수가 `developer_id`를 인자로 받으면서도 `insert_scan_execution()` 호출 시 전달 안 함
- **수정**: `developer_id=developer_id or None` 추가
- **파일**: `dev2/nodes/store.py`

---

## DB 테이블 구조 (핵심 3개)

```
scan_executions
  id          → scan_id (scan_issues와 연결하는 열쇠)
  task_id     → LangGraph 작업 단위 UUID
  pr_id       → GitHub PR 번호
  user_id     → 개발자 UUID (users 테이블 참조, NOT NULL)
  execution_ms → 실행 시간

scan_issues
  scan_id  → scan_executions.id 참조
  agent    → 'static_analysis' | 'security_scan' | 'test_verification' | 'performance'
  severity → 'Critical' | 'Major' | 'Minor'
  rule_id  → Pylint/Bandit 룰 코드 (예: B105, W0611)
  keyword  → M4 연동용 (예: "SQL 인젝션", "N+1 쿼리")

scan_summaries
  scan_id  → scan_executions.id 참조
  critical, major, minor → 이슈 개수 요약
  UNIQUE (scan_id, agent) → 재스캔 시 UPSERT
```

---

## 현재 환경변수 세팅 상태

```bash
# ✅ 설정 완료
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__lsv2_pt_...    # LangSmith 추적 활성화
LANGCHAIN_PROJECT=dev2-wooya
DATABASE_URL=postgresql+asyncpg://...@34.22.101.111:5432/tasklink
POSTGRES_URL=postgresql://...@34.22.101.111:5432/tasklink

# ⚠️ Mock 모드 (실제 LLM 미사용)
USE_MOCK_LLM=true

# ❌ 미설정 (RAG 실제 활성화에 필요)
ANTHROPIC_API_KEY=sk-ant-xxxx
OPENAI_API_KEY=sk-xxxx              # 임베딩 생성용
```

---

## 다음 단계 — 진짜 RAG 켜기

현재 `vector_search_node`는 Mock 모드 (키워드 매칭):
```python
# "sql" 포함 → 무조건 PR-002, PR-005 반환
if any(kw in msg_lower for kw in ("sql", "injection")):
    return [{"pr_id": "PR-002", "similarity": 0.92, ...}]
```

진짜 RAG 활성화 순서:
```bash
# 1. .env에 API 키 추가
OPENAI_API_KEY=sk-xxxx
USE_MOCK_LLM=false

# 2. chunk_embeddings seed 데이터 INSERT (SQL 4개)
#    → sub2_new/docs/learning/ai/rag-vector-search.md §seed 참고

# 3. 서버 재시작 후 POST /scan 재실행
```

---

## 복습 퀴즈 (3문항)

**Q1.** `scan_executions`, `scan_issues`, `scan_summaries` 세 테이블은 어떤 관계인가요?  
왜 하나의 테이블에 다 저장하지 않고 분리했을까요?

<details>
<summary>정답 보기</summary>

`scan_executions`(1행) → `scan_issues`(N행) → `scan_summaries`(에이전트별 요약) 1:N 관계.  
분리 이유: 실행 기록은 한 번만 저장하고, 이슈는 개수가 다르기 때문. 요약은 에이전트별 UPSERT가 필요해서 별도 분리.

</details>

---

**Q2.** `agent` 컬럼에 CHECK 제약이 있는 이유는 무엇인가요?  
`"bandit"`을 허용하지 않고 `"security_scan"`만 허용하는 설계 의도는?

<details>
<summary>정답 보기</summary>

도구 이름(Bandit, ESLint)이 아닌 **역할 이름**(security_scan, static_analysis)으로 저장하는 설계.  
도구가 바뀌어도(Bandit → Semgrep) DB 스키마를 바꿀 필요가 없고, Dev4가 "보안 스캔 결과"를 조회할 때 도구명을 알 필요가 없다.

</details>

---

**Q3.** `USE_MOCK_LLM=true`일 때 `vector_search_node`는 실제 DB 연결을 하나요?

<details>
<summary>정답 보기</summary>

아니요. `use_mock=True`이면 `_get_pool()`을 호출하지 않고 `_mock_search()`로 직접 분기합니다.  
DB 연결 없이 키워드 매칭으로 가짜 유사 이슈를 반환합니다. (`vector_search.py` 346~355줄 참조)

</details>
