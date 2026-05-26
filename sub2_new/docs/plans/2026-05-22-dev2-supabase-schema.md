# Dev 2 — Supabase 테이블 설계 요청서

**프로젝트**: 조직 지식 관리 + 개발자 온보딩 멀티 에이전트 플랫폼
**담당**: Dev 2 (정적 분석 + 보안 스캔 에이전트)
**작성일**: 2026-05-22
**요청 대상**: Supabase 담당자

> Supabase에 아래 3개 테이블 + 인덱스 생성 부탁드립니다.

---

## 테이블 관계 요약

```
scan_executions (1)
    │
    ├──── scan_issues (N)      -- 스캔 1건에 이슈 여러 개
    │
    └──── scan_summaries (2)   -- 스캔 1건에 에이전트별 집계 2행
                                  (static_analysis, security_scan)
```

---

## 테이블 1: `scan_executions`

**역할**: PR 스캔 실행 1건 = 1행

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| `id` | `bigint` | PK, GENERATED ALWAYS AS IDENTITY | 자동 증가 ID |
| `task_id` | `text` | NOT NULL | 오케스트레이터에서 부여하는 UUID |
| `trace_id` | `text` | NOT NULL | LangSmith + agent_traces 연결 키 (`pr_{12hex}` 형식, CLAUDE.md §3) |
| `pr_id` | `text` | NOT NULL | GitHub PR 번호 |
| `developer_id` | `text` | NOT NULL | 개발자 식별자 (GitHub 로그인) |
| `scanned_at` | `timestamptz` | NOT NULL, DEFAULT now() | 스캔 실행 시각 |
| `execution_ms` | `int` | nullable | 전체 스캔 소요 시간 (ms) |

> **[CLAUDE.md §3 준수]** `trace_id`는 `agent_traces.trace_id`와 동일 값을 사용한다.
> 형식: PR 파이프라인 → `pr_{12자리 hex}` / 서브 에이전트 → `{parent_trace_id}_{agent_name}_{4hex}`

```sql
CREATE TABLE scan_executions (
    id            bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    task_id       text        NOT NULL,
    trace_id      text        NOT NULL,   -- agent_traces 연결 (CLAUDE.md §3)
    pr_id         text        NOT NULL,
    developer_id  text        NOT NULL,
    scanned_at    timestamptz NOT NULL DEFAULT now(),
    execution_ms  int
);
```

---

## 테이블 2: `scan_issues`

**역할**: 스캔에서 발견된 개별 이슈 1건 = 1행

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| `id` | `bigint` | PK, GENERATED ALWAYS AS IDENTITY | 자동 증가 ID |
| `scan_id` | `bigint` | NOT NULL, FK → `scan_executions.id` ON DELETE CASCADE | 어느 스캔에서 발생했는지 |
| `agent` | `text` | NOT NULL | `'static_analysis'` 또는 `'security_scan'` |
| `severity` | `text` | NOT NULL | `'Critical'`, `'Major'`, `'Minor'` 중 하나 |
| `rule_id` | `text` | NOT NULL | 룰 식별자 (예: `SEC-001`, `SA-COMPLEXITY`) |
| `file` | `text` | nullable | 이슈 발생 파일 경로 |
| `line` | `int` | nullable | 이슈 발생 라인 번호 |
| `message` | `text` | nullable | 이슈 설명 |
| `suggestion` | `text` | nullable | LLM이 생성한 개선 제안 |
| `similar_issues` | `jsonb` | NOT NULL, DEFAULT `'[]'` | Milvus 유사 이슈 검색 결과 (JSON 배열) |
| `is_false_positive` | `boolean` | NOT NULL, DEFAULT `false` | 개발자가 오탐으로 표시한 경우 true |

```sql
CREATE TABLE scan_issues (
    id                   bigint   GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scan_id              bigint   NOT NULL REFERENCES scan_executions(id) ON DELETE CASCADE,
    agent                text     NOT NULL,   -- 'static_analysis' | 'security_scan'
    severity             text     NOT NULL,   -- 'Critical' | 'Major' | 'Minor'
    rule_id              text     NOT NULL,
    file                 text,
    line                 int,
    message              text,
    suggestion           text,
    similar_issues       jsonb    NOT NULL DEFAULT '[]',
    is_false_positive    boolean  NOT NULL DEFAULT false
);
```

`similar_issues` 컬럼 예시:
```json
[
  { "pr_id": "98", "date": "2026-04-10", "similarity": 0.94, "message": "SQL 파라미터 미처리" },
  { "pr_id": "75", "date": "2026-03-22", "similarity": 0.89, "message": "SQL 인젝션 취약점" }
]
```

> **RAG 용도**: `message` 필드는 llm_judge 노드에서 프롬프트에 "과거 유사 사례" 컨텍스트로 주입됩니다.

---

## 테이블 3: `scan_summaries`

**역할**: 스캔 1건의 severity별 집계 (빠른 인사이트 조회용)

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| `id` | `bigint` | PK, GENERATED ALWAYS AS IDENTITY | 자동 증가 ID |
| `scan_id` | `bigint` | NOT NULL, FK → `scan_executions.id` ON DELETE CASCADE | 어느 스캔의 집계인지 |
| `agent` | `text` | NOT NULL | `'static_analysis'` 또는 `'security_scan'` |
| `critical` | `int` | NOT NULL, DEFAULT 0 | Critical 이슈 수 |
| `major` | `int` | NOT NULL, DEFAULT 0 | Major 이슈 수 |
| `minor` | `int` | NOT NULL, DEFAULT 0 | Minor 이슈 수 |
| _(UNIQUE)_ | | `UNIQUE (scan_id, agent)` | 동일 스캔+에이전트 중복 방지 |

```sql
CREATE TABLE scan_summaries (
    id        bigint  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scan_id   bigint  NOT NULL REFERENCES scan_executions(id) ON DELETE CASCADE,
    agent     text    NOT NULL,
    critical  int     NOT NULL DEFAULT 0,
    major     int     NOT NULL DEFAULT 0,
    minor     int     NOT NULL DEFAULT 0,
    CONSTRAINT uq_scan_summaries_scan_agent UNIQUE (scan_id, agent)
);
```

---

## 인덱스 요청

| 인덱스명 | 테이블 | 컬럼 | 타입 | 이유 |
|---------|--------|------|------|------|
| `idx_scan_executions_scanned_at` | `scan_executions` | `scanned_at` | BRIN | 시계열 조회, B-tree 대비 크기 90% 절감 |
| `idx_scan_executions_developer_time` | `scan_executions` | `(developer_id, scanned_at DESC)` | B-tree 복합 | 개인별 인사이트 쿼리 |
| `idx_executions_developer_covering` | `scan_executions` | `(developer_id) INCLUDE (id, scanned_at)` | 커버링 | 테이블 스캔 제거 |
| `idx_scan_issues_scan_id` | `scan_issues` | `scan_id` | B-tree | FK JOIN 성능 |
| `idx_scan_issues_rule_severity` | `scan_issues` | `(rule_id, severity)` | B-tree 복합 | 팀별 Top5 GROUP BY |
| `idx_scan_issues_critical` | `scan_issues` | `(scan_id, rule_id) WHERE severity = 'Critical'` | 부분 인덱스 | Critical 에스컬레이션 조회 전용 |
| `idx_scan_issues_similar` | `scan_issues` | `similar_issues` | GIN | JSONB 검색 |
| `idx_scan_summaries_scan_id` | `scan_summaries` | `scan_id` | B-tree | FK JOIN 성능 |

```sql
-- BRIN: scanned_at 시계열
CREATE INDEX idx_scan_executions_scanned_at
    ON scan_executions USING brin (scanned_at);

-- 복합: developer 인사이트 쿼리 (equality 먼저, range 나중)
CREATE INDEX idx_scan_executions_developer_time
    ON scan_executions (developer_id, scanned_at DESC);

-- 커버링: /insights/developer 쿼리 테이블 스캔 제거
CREATE INDEX idx_executions_developer_covering
    ON scan_executions (developer_id)
    INCLUDE (id, scanned_at);

-- FK 인덱스: JOIN 성능
CREATE INDEX idx_scan_issues_scan_id    ON scan_issues (scan_id);
CREATE INDEX idx_scan_summaries_scan_id ON scan_summaries (scan_id);

-- 복합: 팀별 Top5 GROUP BY rule_id, severity
CREATE INDEX idx_scan_issues_rule_severity
    ON scan_issues (rule_id, severity);

-- 부분 인덱스: Critical만 (전체의 5~10%)
CREATE INDEX idx_scan_issues_critical
    ON scan_issues (scan_id, rule_id)
    WHERE severity = 'Critical';

-- GIN: similar_issues JSONB 검색
CREATE INDEX idx_scan_issues_similar
    ON scan_issues USING gin (similar_issues);
```

---

## 참고: 이 테이블을 사용하는 API 엔드포인트

| 엔드포인트 | 사용 테이블 | 주요 쿼리 조건 | 비고 |
|-----------|------------|--------------|------|
| `POST /scan` | `scan_executions`, `scan_issues`, `scan_summaries` | INSERT | n8n Webhook 트리거 |
| `GET /insights/developer/{id}` | `scan_issues` JOIN `scan_executions` | `WHERE developer_id = ?` GROUP BY | — |
| `GET /insights/team` | `scan_issues` JOIN `scan_executions` | `WHERE scanned_at >= 이번달` GROUP BY LIMIT 5 | — |
| `GET /insights/trends` | `scan_summaries` JOIN `scan_executions` | GROUP BY week, developer_id | — |
| _(내부)_ escalate | `scan_issues` | `WHERE severity = 'Critical'` | Critical 발견 시 Dev4에 자동 알림 (DB 쓰기 없음) |
| `PATCH /issues/{id}/dismiss` | `scan_issues` | `UPDATE SET is_false_positive = true` | 개발자 오탐 표시 |

---

## 참고: scan_summaries 적재 방식

재스캔 시 중복 삽입 방지를 위해 UPSERT로 처리합니다.

```sql
INSERT INTO scan_summaries (scan_id, agent, critical, major, minor)
VALUES ($1, $2, $3, $4, $5)
ON CONFLICT (scan_id, agent)
DO UPDATE SET
    critical = EXCLUDED.critical,
    major    = EXCLUDED.major,
    minor    = EXCLUDED.minor;
```
