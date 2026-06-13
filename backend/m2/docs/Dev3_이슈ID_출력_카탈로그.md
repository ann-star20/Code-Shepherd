# 📋 Dev3 — 테스트/성능 에이전트 전체 출력 카탈로그

> 테스트 커버리지·성능 평가에서 **나올 수 있는 모든 이슈 ID와 출력**을 정리한 문서.
> (TEST-001/003/004, PERF-001/002/003 + 메트릭 + 최종 출력 구조)

---

## 1. 에이전트 2종 → 이슈 ID 6종

탐지기 6개가 두 에이전트로 묶여 나간다. (`main.py`)

| 에이전트 | 탐지기 파일 | rule_id | severity | 무엇을 잡나 |
|----------|------------|---------|----------|------------|
| **test_verification** | `coverage.py` | **TEST-001** | Major | 라인 커버리지 < 80% |
| **test_verification** | `missing_funcs.py` | **TEST-004** | Minor | 본문이 실행 안 된(=테스트 안 된) 함수 |
| **test_verification** | `edge_cases.py` | **TEST-003** | Minor | 빠진 엣지케이스 (※ main 미연결) |
| **performance** | `complexity.py` | **PERF-001** | Minor/Major | 중첩 루프 복잡도 |
| **performance** | `nplus1.py` | **PERF-002** | Major | 루프 안 DB 호출 (N+1) |
| **performance** | `memory_leak.py` | **PERF-003** | Minor | 메모리 누수 패턴 (※ main 미연결) |

> ⚠️ **TEST-003 / PERF-003은 `main.run()`에 연결 안 됨** — eval 골든 라벨 보호 목적(TECH_SPEC §6).
> 코드·테스트는 존재하지만 실제 파이프라인 출력엔 안 나온다.
> 현재 실제로 나오는 건 **TEST-001, TEST-004, PERF-001, PERF-002** 4종.

---

## 2. 각 이슈 ID 상세

### TEST-001 — 라인 커버리지 미달 (Major)
- **조건**: `coverage_line < 0.80` (`COVERAGE_THRESHOLD`)
- **file**: `"(전체)"`, **line**: `null`
- **message 예**: `테스트 라인 커버리지 20.0% < 기준 80%.`
- **suggestion**: `테스트를 추가해 커버리지를 80% 이상으로 올리세요.`

### TEST-004 — 누락 함수 (Minor)
- **조건**: 함수 본문(`body[0].lineno` ~ `end_lineno`)이 `executed_lines`와 교집합 0
- def 줄은 import 시 항상 실행되므로 **본문 라인**으로 판정 (def-line 함정 회피)
- **message 예**: `함수 'get_posts'에 대한 테스트 실행 흔적이 없습니다.`
- **suggestion**: `get_posts()에 대한 단위 테스트를 추가하세요.`

### TEST-003 — 누락 엣지케이스 (Minor) *(main 미연결)*
- **LLM 모드**(API 키 有): 함수 소스 → Gemini → 빠진 엣지케이스 목록
- **휴리스틱 모드**(키 無): 인자명 키워드 매칭 → 메시지에 `[heuristic]` 접두사
  - 예: `price` → `0 (zero price)`, `negative price` / `ids` → `empty list []`, `None`
- **message 예**: `[heuristic] 함수 'calc_price': 빠진 엣지케이스 — 0 (zero price), negative price`

### PERF-001 — 시간복잡도 (Minor/Major)
- **depth 2** → Minor `O(n^2)` / **depth 3+** → Major `O(n^3)+`
- comprehension은 단일 루프로 간주(중첩 깊이 미포함)
- **message 예**: `O(n^2) 시간복잡도: 2중 중첩 루프가 감지되었습니다.`

### PERF-002 — N+1 쿼리 (Major)
- **조건**: `for`/`while` 본문 안에서 DB 호출 메서드 발견
- **DB 메서드 집합**: `query, execute, filter, fetchone, fetchall, scalar`
- **제외**: `.get/.all/.first/.count`(일반 이름 충돌), `self.method()`(자기참조)
- **message 예**: `N+1 쿼리: 루프 안에서 DB 호출이 반복됩니다.`

### PERF-003 — 메모리 누수 (Minor) *(main 미연결)*
- **패턴 ①**: `open()`이 with/대입 없이 단독 호출 → 파일 핸들 누수
- **패턴 ②**: 전역 list/dict에 함수 내부에서 `append` 누적 → 무한 증가
- LLM 모드 시 confidence < 0.7 후보 제외
- **message 예**: `[heuristic] 메모리 누수 가능: open() called without with-statement...`

---

## 3. 메트릭 (test_verification 에이전트의 `metrics`)

`coverage.measure()`만 측정치를 내보낸다. (performance는 항상 `metrics: null`)

| metrics 키 | 의미 | 출력 조건 |
|-----------|------|----------|
| `coverage_line` | 라인 커버리지 (0~1) | 항상 |
| `coverage_branch` | 브랜치 커버리지 | `--cov-branch` 데이터 있을 때만 (없으면 **키 자체 제외**) |
| `coverage_func` | 함수 본문 커버리지 (AST 기반) | 함수가 1개 이상일 때 |

> null 금지 원칙: 데이터 없으면 값을 `null`로 넣지 않고 **키를 통째로 뺀다.**

---

## 4. 최종 출력 구조 (AgentOutput)

`run()`은 **항상 2개**의 `AgentOutput`을 리스트로 반환 (`[test_verification, performance]`):

```json
{
  "task_id": "demo-task-001",
  "scan_id": 1,
  "pr_id": "PR-demo",
  "agent": "test_verification",        // 또는 "performance"
  "issues": [ { "severity": "...", "file": "...", "line": 0, "message": "...", "rule_id": "...", "suggestion": "..." } ],
  "summary": { "critical": 0, "major": 1, "minor": 2 },
  "metrics": { "coverage_line": 0.2, "coverage_func": 0.25 },  // performance는 null
  "execution_ms": 5
}
```

- **summary**: 이슈를 severity별로 집계 (`assemble/output.py`)
- **severity 종류**: `Critical` / `Major` / `Minor` (현재 Critical 내는 탐지기는 없음)

---

## 5. diff 교집합 필터

모든 이슈는 마지막에 `filter_issues()`로 **PR diff에서 바뀐 라인과 겹치는 것만** 남긴다.
(TEST-001은 file=`(전체)`라 필터 통과) → 바뀌지도 않은 코드에 대한 오탐 방지.

---

## 6. 실제 데모 출력 (`demo_output.json` 기준)

`python main.py` 실행 시 fixture 레포(`sample_repo`)에서 실제로 나온 결과:

- **test_verification**: TEST-001(Major) ×1, TEST-004(Minor) ×2
  → `major:1, minor:2`, `coverage_line:0.2, coverage_func:0.25`
- **performance**: PERF-002(Major) ×1, PERF-001(Minor) ×1
  → `major:1, minor:1`, `metrics:null`

---

## 부록: 빠른 참조표

| rule_id | 에이전트 | severity | 탐지기 | main 연결 |
|---------|----------|----------|--------|:---------:|
| TEST-001 | test_verification | Major | coverage.py | ✅ |
| TEST-003 | test_verification | Minor | edge_cases.py | ❌ |
| TEST-004 | test_verification | Minor | missing_funcs.py | ✅ |
| PERF-001 | performance | Minor/Major | complexity.py | ✅ |
| PERF-002 | performance | Major | nplus1.py | ✅ |
| PERF-003 | performance | Minor | memory_leak.py | ❌ |
