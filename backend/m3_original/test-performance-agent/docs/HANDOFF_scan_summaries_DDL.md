# 📨 [Dev2 전달용] scan_summaries 테이블 생성 요청

> **From**: Dev3 (test-performance-agent)
> **To**: Dev2 (공유 DB 담당)
> **요청**: 공유 GCP DB(`tasklink`)에 `scan_summaries` 테이블 1회 생성
> **확인일**: 2026-06-01 — 현재 GCP에 이 테이블 없음 (`scan_executions`, `scan_issues`만 존재)

---

## 1. 한 줄 요청

> Dev3의 분석 결과 **요약(severity 집계) + 커버리지 측정치**를 저장할 `scan_summaries` 테이블이 필요합니다. 아래 DDL 그대로 실행 부탁드립니다.

---

## 2. 왜 필요한가

- `scan_issues`는 **이슈 하나하나**(N+1, 커버리지 부족 등)를 1행씩 저장 → 너무 상세함.
- Dev4(평가)가 verdict 판정 시 **"Major 몇 개?"** 같은 집계를 매번 COUNT 하면 느림 → **요약 행**이 필요.
- 커버리지 측정치(`coverage_line/branch/func`)를 시계열로 쌓아 **신입 성장 추적**에 사용 → `metrics` 컬럼 필요.

→ `scan_issues`(상세) + `scan_summaries`(요약) = 형제 관계. Dev2의 정적분석·보안도 같은 표 공유.

---

## 3. DDL (이대로 실행)

```sql
CREATE TABLE IF NOT EXISTS scan_summaries (
    id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scan_id   bigint NOT NULL
              REFERENCES scan_executions(id) ON DELETE CASCADE,
    agent     text NOT NULL
              CHECK (agent IN ('static_analysis','security_scan',
                               'test_verification','performance')),
    critical  int  NOT NULL DEFAULT 0,
    major     int  NOT NULL DEFAULT 0,
    minor     int  NOT NULL DEFAULT 0,
    metrics   jsonb,                       -- 커버리지 등. NULL = 측정 안 함
    CONSTRAINT uq_scan_summaries_scan_agent UNIQUE (scan_id, agent)
);
```

---

## 4. 컬럼 설명

| 컬럼 | 의미 |
|---|---|
| `id` | 자동 증가 PK |
| `scan_id` | 어느 PR 스캔인지 (→ `scan_executions.id` FK) |
| `agent` | 어느 에이전트 결과인지. **Dev3는 `test_verification` / `performance` 사용** (Dev2는 `static_analysis` / `security_scan`) |
| `critical/major/minor` | severity별 이슈 개수 (집계) |
| `metrics` | 커버리지 등 측정치. 예: `{"coverage_line":0.20,"coverage_branch":0.0,"coverage_func":0.25}`. **0~1 소수.** 성능/보안 에이전트는 NULL |
| `UNIQUE(scan_id, agent)` | 한 스캔×한 에이전트당 요약 1행. 재실행 시 UPSERT로 갱신 |

---

## 5. 기존 스키마와의 관계

```
scan_executions (PR 스캔 1건)
   ├── scan_issues      (이슈 N건)      ← 이미 존재
   └── scan_summaries   (요약 = 에이전트당 1행)  ← 이번에 추가 요청
```

- **기존 테이블 변경 없음.** 신규 테이블 1개만 추가.
- `scan_issues.agent` CHECK에는 이미 `test_verification`/`performance`가 포함돼 있어, 동일 허용값을 `scan_summaries`에도 적용했습니다.

---

## 6. Dev3의 사용 방식 (참고)

```sql
-- Dev3가 실행하는 쿼리 (persist.py → persist_pg)
INSERT INTO scan_summaries (scan_id, agent, critical, major, minor, metrics)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (scan_id, agent) DO UPDATE SET
    critical = excluded.critical, major = excluded.major,
    minor = excluded.minor, metrics = excluded.metrics;
```

- `scan_executions` 행은 **Dev1이 PR당 1건 생성** → Dev3는 그 `scan_id`를 받아 자식 행만 추가 (Dev3는 `scan_executions`를 만들지 않음).
- 재스캔 시 중복 방지 위해 **UPSERT**(ON CONFLICT) 사용.

---

## 7. 검증 완료 (참고)

Dev3 쪽 코드(`persist_pg`)는 이미 이 DDL과 동일 구조로 **트랜잭션+롤백 통합 테스트 통과**했습니다 (scan_issues 5행 + scan_summaries 2행 적재·readback 확인, 공유 DB 변경 0). 표만 생성되면 즉시 실저장 가능합니다.

---

## 8. 생성 후 Dev3가 할 일

표 생성 완료 알려주시면:
1. `persist_pg`에서 `CREATE TABLE IF NOT EXISTS` 제거 (이제 표가 영구 존재하므로 불필요)
2. 실제 INSERT 1회 검증 (롤백 아닌 실커밋)
3. 진행상황.md Task 17 완료 표시

---

*문의: Dev3 / 근거 문서: DEV3_TECH_SPEC.md §11*
