# M2/M3 평가 데이터 DB 스키마

> **실제 코드 기준**: `sub2_new/dev2/schema.py` (M2), `test-performance-agent/contracts.py` (M3), `test-performance-agent/HANDOFF_scan_summaries_DDL.md` (M3 DDL)

---

## 전체 흐름

```
[데이터셋 적재]
cases            ← dataset_manifest.json
expected_issues  ← 각 케이스 expected_issue.json

[에이전트 실행 결과 적재]
scan_executions  ← PR 1건당 1행 (Dev1이 생성)
scan_issues      ← M2/M3 탐지 이슈 (이슈당 1행)
scan_summaries   ← M2/M3 요약 집계 (에이전트당 1행)

[채점]
eval_results     ← expected_issues vs scan_issues 비교 결과
```

---

## 테이블 1: cases (케이스 목록)

**적재 출처:** `datasets/dataset_manifest.json`

```sql
CREATE TABLE cases (
  case_id      VARCHAR PRIMARY KEY,
  module       VARCHAR NOT NULL,   -- 'M2' | 'M3'
  source       VARCHAR,            -- 'Task-Link Custom' | 'BugsInPy' | 'OWASP'
  case_type    VARCHAR,            -- 'security' | 'test_performance' | 'mixed_project'
  domain       VARCHAR,            -- 예: '주문 서비스' (mixed 케이스만 있음)
  target_path  VARCHAR,            -- 예: 'm3_mixed_project_cases/mixed_case_001'
  rule_ids     TEXT[],             -- 예: ARRAY['PERF-001', 'PERF-002', 'TEST-001']
  created_at   TIMESTAMP DEFAULT NOW()
);
```

---

## 테이블 2: expected_issues (정답지)

**적재 출처:** 각 케이스 폴더의 `expected_issue.json`

> 케이스 1개에 이슈 여러 개 → 행 여러 개로 나눠 적재.
> M2/M3 필드가 다른 부분은 주석으로 표시.

```sql
CREATE TABLE expected_issues (
  id                  SERIAL PRIMARY KEY,
  case_id             VARCHAR REFERENCES cases(case_id),
  module              VARCHAR NOT NULL,  -- 'M2' | 'M3'
  rule_id             VARCHAR NOT NULL,  -- 예: 'SEC-001' | 'PERF-002'
  severity            VARCHAR,           -- 'Critical' | 'Major' | 'Minor'

  -- 공통
  file                VARCHAR,           -- 예: 'app/order_service.py'
  line                INTEGER,           -- 몇 번째 줄 (M3는 NULL일 수 있음)
  message             TEXT,              -- 이슈 설명
  suggestion          TEXT,              -- 수정 방법

  -- M2 전용
  issue_type          VARCHAR,           -- 'Bug' | 'Vulnerability' | 'Code Smell'
  resolution_example  TEXT,              -- 수정 예시 코드
  similar_issues      JSONB,             -- 연관 rule_id 목록 [{rule_id, reason}]
  cwe                 VARCHAR,           -- 예: 'CWE-89' (OWASP 케이스만)
  real_vulnerability  BOOLEAN,           -- true/false (OWASP 케이스만)
  category            VARCHAR,           -- 예: 'sqli' (OWASP 케이스만)

  -- M3 전용
  target_function     VARCHAR,           -- 예: 'load_orders_with_items'
  evidence            TEXT               -- 왜 이슈인지 구체적 근거
);
```

---

## 테이블 3: scan_executions (PR 스캔 실행 단위)

**적재 시점:** Dev1(Orchestrator)이 PR 수신 시 1행 생성

> `scan_issues`, `scan_summaries`의 부모 테이블. Dev3는 이 테이블을 만들지 않고 scan_id만 받아서 사용.

```sql
CREATE TABLE scan_executions (
  id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  task_id      VARCHAR NOT NULL,   -- 에이전트 실행 단위 UUID
  trace_id     VARCHAR,            -- CLAUDE.md §3 형식 예: 'pr_3a9f1c2b44e0'
  pr_id        VARCHAR NOT NULL,   -- GitHub PR 번호
  developer_id VARCHAR,
  execution_ms INTEGER,
  created_at   TIMESTAMP DEFAULT NOW()
);
```

---

## 테이블 4: scan_issues (M2/M3 탐지 이슈)

**적재 시점:** M2 또는 M3 에이전트 실행 후, 이슈당 1행

> M2는 `dev2/db.py`의 `insert_scan_issues()` 사용.
> M2/M3 공통 필드 + M2 전용 필드 구분.

```sql
CREATE TABLE scan_issues (
  id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  scan_id      BIGINT NOT NULL REFERENCES scan_executions(id) ON DELETE CASCADE,
  agent        TEXT NOT NULL
               CHECK (agent IN (
                 'static_analysis', 'security_scan',   -- M2
                 'test_verification', 'performance'     -- M3
               )),

  -- 공통
  severity     TEXT NOT NULL,   -- 'Critical' | 'Major' | 'Minor'
  rule_id      TEXT NOT NULL,   -- 예: 'SEC-001' | 'PERF-002'
  file         TEXT,
  line         INTEGER,         -- M3는 NULL일 수 있음
  message      TEXT,
  suggestion   TEXT,

  -- M2 전용 (M3는 NULL)
  issue_type          TEXT,     -- 'Bug' | 'Vulnerability' | 'Code Smell'
  resolution_example  TEXT,
  similar_issues      JSONB,    -- [{rule_id, reason}]
  status              TEXT DEFAULT 'Open',  -- 'Open' | 'Accepted' | 'False Positive'

  -- M2 M4 피드백 전용 (M3는 NULL)
  keyword              TEXT,    -- 예: 'SQL Injection'
  sub_category         TEXT,    -- 예: 'raw_query'
  concept_id           TEXT,    -- 예: 'sql_injection'
  confidence_score     FLOAT,   -- 0.0~1.0
  code_snippet         TEXT,    -- 문제 코드 조각
  name_of_function     TEXT,    -- 이슈 발생 라인을 감싸는 함수명 (함수 밖이면 '')
  learning_context     JSONB,   -- {framework, language, domain_context}
  code_context         JSONB,   -- {context_before, issue_line, context_after}
  taxonomy             JSONB,   -- {category, subcategory, issue_type, sub_issue_type}

  created_at   TIMESTAMP DEFAULT NOW()
);
```

---

## 테이블 5: scan_summaries (M2/M3 요약 집계)

**적재 시점:** 각 에이전트 실행 완료 후, 에이전트당 1행

> M3 `HANDOFF_scan_summaries_DDL.md` 기준. 재실행 시 UPSERT로 갱신.

```sql
CREATE TABLE IF NOT EXISTS scan_summaries (
  id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  scan_id   BIGINT NOT NULL REFERENCES scan_executions(id) ON DELETE CASCADE,
  agent     TEXT NOT NULL
            CHECK (agent IN (
              'static_analysis', 'security_scan',   -- M2
              'test_verification', 'performance'     -- M3
            )),
  critical  INT NOT NULL DEFAULT 0,
  major     INT NOT NULL DEFAULT 0,
  minor     INT NOT NULL DEFAULT 0,
  metrics   JSONB,  -- M3 커버리지용. 예: {"coverage_line":0.20,"coverage_branch":0.0}
                    -- M2 성능/보안 에이전트는 NULL
  CONSTRAINT uq_scan_summaries_scan_agent UNIQUE (scan_id, agent)
);
```

**M3 UPSERT 예시:**
```sql
INSERT INTO scan_summaries (scan_id, agent, critical, major, minor, metrics)
VALUES (%s, 'test_verification', %s, %s, %s, %s)
ON CONFLICT (scan_id, agent) DO UPDATE SET
  critical = excluded.critical,
  major    = excluded.major,
  minor    = excluded.minor,
  metrics  = excluded.metrics;
```

---

## 테이블 6: eval_results (채점 결과)

**적재 시점:** `expected_issues` vs `scan_issues` 비교 후, 케이스당 1행

```sql
CREATE TABLE eval_results (
  id         SERIAL PRIMARY KEY,
  scan_id    BIGINT REFERENCES scan_executions(id),
  case_id    VARCHAR REFERENCES cases(case_id),
  module     VARCHAR NOT NULL,   -- 'M2' | 'M3'
  verdict    VARCHAR NOT NULL,   -- 'PASS' | 'FAIL'
  fn_list    TEXT[],             -- 놓친 rule_id (False Negative)
  fp_list    TEXT[],             -- 오탐 rule_id (False Positive)
  created_at TIMESTAMP DEFAULT NOW()
);
```

**채점 로직:**
```python
expected = {e.rule_id for e in expected_issues where case_id = 'xxx'}
actual   = {s.rule_id for s in scan_issues where scan_id = N}

fn = expected - actual    # 정답인데 못 잡음
fp = actual - expected    # 잡았는데 정답 아님
verdict = 'PASS' if not fn and not fp else 'FAIL'
```

---

## 테이블 간 관계

```
cases ──────────────────── expected_issues (1:N)
  │
  └── eval_results (case_id FK)
            │
scan_executions ─────────── scan_issues (1:N)
      │                              │
      └── scan_summaries (1:N)       └── eval_results (scan_id FK)
```

---

## 주요 조회 쿼리

```sql
-- M2/M3 모듈별 PASS/FAIL 집계
SELECT module,
       COUNT(*) FILTER (WHERE verdict = 'PASS') AS pass,
       COUNT(*) FILTER (WHERE verdict = 'FAIL') AS fail
FROM eval_results
GROUP BY module;

-- 가장 많이 놓치는 rule_id 순위
SELECT rule_id, COUNT(*) AS 누락횟수
FROM eval_results, unnest(fn_list) AS rule_id
GROUP BY rule_id
ORDER BY 누락횟수 DESC;

-- 특정 케이스 정답 vs 실제 비교
SELECT e.rule_id AS 정답, s.rule_id AS 탐지결과
FROM expected_issues e
LEFT JOIN scan_issues s
  ON s.scan_id = (SELECT id FROM scan_executions WHERE task_id = 'uuid-here')
  AND e.rule_id = s.rule_id
WHERE e.case_id = 'm3_mixed_001_order_service';

-- M3 커버리지 시계열 조회
SELECT se.created_at, ss.metrics->>'coverage_line' AS 커버리지
FROM scan_summaries ss
JOIN scan_executions se ON ss.scan_id = se.id
WHERE ss.agent = 'test_verification'
ORDER BY se.created_at;
```
