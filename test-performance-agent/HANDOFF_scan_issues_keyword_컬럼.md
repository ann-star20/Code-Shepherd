# 📦 핸드오프 — scan_issues keyword 3컬럼 (Dev2/팀 합의 후 적용)

> 인수인계 §3.5 구현. **Dev3 쪽 코드는 완료**(모델·탐지기·로컬 DB, 테스트 통과).
> 아래 GCP 공유 DB 변경은 **운영 장애를 막기 위해 팀 합의 후 "한 번에" 적용**해야 함.
> (지금 게이트웨이 INSERT만 먼저 바꾸면, GCP 표에 컬럼이 없어 PR 분석 저장이 통째로 실패함.)

---

## 0. 무엇을 / 왜

이슈를 Dev4가 통계 내기 쉽게 **3칸으로 정규화**:

| 컬럼 | 의미 | 예시 |
|---|---|---|
| `keyword` | 대분류 (고정 한글 라벨 → `GROUP BY keyword` 통계 키) | `N+1 쿼리` |
| `sub_keyword` | 세부 대상 (어디서/무엇이) | `load_cart_items`, `src/cart.py:8` |
| `metric_value` | 수치 (있을 때만, 없으면 빈 문자열) | `26.7%` |

---

## 1. ✅ 이미 완료 (Dev3 소유, 적용됨)

- `contracts.py` `Issue` 모델에 `keyword`/`sub_keyword`/`metric_value` 추가 (기본 빈 문자열 → 기존 호출 100% 호환).
- 탐지기 6개가 §3.5 표대로 채움 (아래 표).
- 로컬 데모 DB(`persist.py` SQLite) 스키마·INSERT 반영 + 라운드트립 테스트 통과.
- 테스트: `tests/test_keyword_columns.py` (8건) + 전체 139건 PASS.

### 탐지기별 채우는 값 (실제 구현값)

| rule_id | keyword | sub_keyword | metric_value |
|---|---|---|---|
| TEST-001 (커버리지) | `커버리지 미충족` | `(전체)` | 라인% 예: `20.0%` |
| TEST-004 (테스트 누락) | `테스트 누락` | 함수명 | (빈값) |
| TEST-003 (엣지케이스)\* | `엣지케이스 누락` | 함수명 | (빈값) |
| PERF-002 (N+1) | `N+1 쿼리` | `파일:줄` 예: `src/cart.py:8` | (빈값, 향후 A2 쿼리횟수) |
| PERF-001 (복잡도) | `시간복잡도` | `O(n^2)` 등 | (빈값) |
| PERF-003 (메모리)\* | `메모리 누수` | `파일:줄` | (빈값) |

> \* TEST-003·PERF-003은 `main.run()`에 미연결(eval 골든 라벨 보호, TECH_SPEC §6) — 컬럼은 채워두었고, 추후 연결 시 그대로 흐름.
> ⚠️ PERF-001 `sub_keyword`는 `O(n^2)`만 넣음. §3.5의 "O(n^2) + 함수명"에서 **함수명은 현재 탐지기가 추적 안 함**(최상위 루프 기준 탐지). 함수명까지 넣으려면 별도 작업 필요 → 향후 과제로 분리.

---

## 2. ⏳ 팀 합의 후 적용 (GCP 공유 DB — 아래 3개를 같은 PR로 묶어 원자 적용)

### (A) GCP Postgres — scan_issues 컬럼 추가
```sql
ALTER TABLE scan_issues
  ADD COLUMN IF NOT EXISTS keyword      text DEFAULT '',
  ADD COLUMN IF NOT EXISTS sub_keyword  text DEFAULT '',
  ADD COLUMN IF NOT EXISTS metric_value text DEFAULT '';
```

### (B) `webhook-gateway/agents/dev3_adapter.py` — dict에 3키 추가
`analyze()`의 issues.append({...}) 에:
```python
issues.append({
    "severity": i.severity, "file": i.file, "line": i.line,
    "message": i.message, "rule_id": i.rule_id,
    "suggestion": i.suggestion, "_agent": o.agent,
    "keyword": i.keyword, "sub_keyword": i.sub_keyword,   # ← 추가
    "metric_value": i.metric_value,                       # ← 추가
})
```

### (C) `webhook-gateway/gateway.py` `_persist_to_db` — scan_issues INSERT에 3컬럼
```python
cur.execute("""
    INSERT INTO scan_issues
      (scan_id, agent, severity, rule_id, file, line, message, suggestion,
       keyword, sub_keyword, metric_value)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
""", (scan_id, ag, i["severity"], i.get("rule_id", ""),
      i.get("file", ""), i.get("line"), i.get("message", ""),
      i.get("suggestion", ""),
      i.get("keyword", ""), i.get("sub_keyword", ""), i.get("metric_value", "")))
```

> **적용 순서**: (A) ALTER 먼저 → 그 다음 (B)(C) 코드 배포. 순서 어기면 운영 INSERT 실패.

---

## 3. Dev4에게 공유할 메시지 (제안)

> "이슈를 요청하신 2칸 대신 **3칸**(`keyword` 대분류 / `sub_keyword` 세부 / `metric_value` 수치)으로
>  정규화했습니다. `GROUP BY keyword`로 바로 통계(예: 'N+1 쿼리 이번 달 8회'), `metric_value`로
>  수치만 따로(예: 26.7% → 성장그래프) 쓰실 수 있습니다. 위 표가 탐지기별 채우는 값입니다."
