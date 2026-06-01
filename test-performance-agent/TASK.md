# Dev3 TASKS — TDD 모듈 분해

> 한 번에 한 태스크. 통과 전엔 다음 시작 X. 매 태스크는 PRD §5.4 부정 케이스 포함.

## Task 1. contracts.py
- **입력**: 없음 (Pydantic 모델 정의)
- **출력**: `RepoInfo`, `Developer`, `Dev3Context`, `Dev3Input`, `Issue`, `SummaryCount`, `AgentOutput`
- **Red 테스트**:
  - `Issue(severity="WrongValue", ...)` → ValidationError
  - `AgentOutput(... metrics={"coverage_line": 0.2}, ...)` 정상 생성
  - `AgentOutput.summary.major += 1` 동작
- **완료기준**: 모든 모델 생성/검증 테스트 5+ PASS

## Task 2. config/settings.py
- **입력/출력**: 상수 일원화
- **Red 테스트**: 
  - `COVERAGE_THRESHOLD == 0.80`, `DB_CALL_NAMES`가 좁은 집합(query/execute/filter/fetchone/fetchall/scalar) 포함
- **완료기준**: 상수 import + 기본값 확인 테스트 3+ PASS
- **§18 원칙**: DB_CALL_NAMES는 좁게 시작 (확장은 옵션)

## Task 3. assemble/output.py
- **입력**: `task_id, scan_id, pr_id, agent, issues[], metrics, execution_ms`
- **출력**: `AgentOutput`
- **Red 테스트**:
  - 빈 이슈 → summary 모두 0
  - severity 카운트 정확 (3 Critical 2 Major 5 Minor)
  - performance agent에 metrics=None 허용
- **완료기준**: 4+ PASS

## Task 4. test_verification/coverage.py
- **입력**: `repo_path` (`coverage.json` 있어야 함)
- **출력**: `(list[Issue], metrics: dict | None)`
- **Red 테스트** (긍정·부정 둘 다):
  - 라인 20% → TEST-001 Major + coverage_line=0.2
  - 라인 90% → 0 issue
  - coverage.json 없음 → ([], None)
  - num_statements=0 → metrics 비우거나 None
  - branch 데이터 있음 → coverage_branch 산출
  - func 커버리지 AST 계산 (def-line만 실행이면 func 0.0)
- **완료기준**: 6+ PASS

## Task 5. test_verification/missing_funcs.py
- **입력**: `repo_path`, `changed`
- **출력**: `list[Issue]`
- **Red 테스트**:
  - 두 함수 본문 다 실행 → 0
  - 한 함수 본문 미실행 → 1 (그 함수만)
  - ★ **def 줄만 실행되고 본문 미실행 → 둘 다 잡혀야 함** (함정 케이스)
  - coverage.json 없음 → graceful 0
- **완료기준**: 4+ PASS, def-line 함정 테스트 포함

## Task 6. performance/nplus1.py
- **입력**: `repo_path`, `changed`
- **출력**: `list[Issue]` (PERF-002 Major)
- **Red 테스트 (긍정)**:
  - for 루프 안 `.query()` → 1 issue
  - while + `.execute()` → 1 issue
  - 중첩 루프 + 내부 `.filter()` → 1 issue
- **Red 테스트 (부정 — 어제 발견한 함정)**:
  - ★ 루프 안 `.get()` / `.all()` / `.first()` / `.count()` → **0 issue** (DB_CALL_NAMES에서 제외)
  - 루프 밖 단일 `.query()` → 0 issue
  - `self.query()` 자기참조 → 0 issue
  - 루프 안 일반 산술 → 0 issue
- **완료기준**: 7+ PASS, **부정 케이스가 긍정보다 많아야 함**

## Task 7. performance/complexity.py
- **입력**: `repo_path`, `changed`
- **출력**: `list[Issue]` (PERF-001)
- **Red 테스트**:
  - 루프 없음 → 0
  - 단일 루프 → 0
  - 이중 중첩 → 1 Minor (O(n²))
  - 삼중 중첩 → 1 Major (O(n³))
  - 비중첩 인접 단일 루프 2개 → 0
  - list comprehension → 단일 루프로 간주 (0)
- **완료기준**: 6+ PASS

## Task 8. filter/diff_filter.py
- **입력**: `pr_diff: str` / `issues, changed, repo_path`
- **출력**: `changed: dict[str, set[int]]` / 필터된 `issues`
- **Red 테스트**:
  - 헌크 파싱: `+`줄만 changed에 추가
  - file=="(전체)" 또는 line==None → 무조건 유지
  - diff 밖 파일 이슈 → drop
  - 바뀐 줄의 함수 범위(1-hop) 안 이슈 → 유지
- **완료기준**: 5+ PASS

## Task 9. main.py (run)
- **입력**: `Dev3Input`, (옵션 `repo_path`)
- **출력**: `list[AgentOutput]` (test_verification + performance)
- **Red 테스트** (탐지기는 mock):
  - mocked 탐지기 결과 → 정확히 2개 AgentOutput 반환
  - 한 탐지기가 Exception 던지면 → 그 탐지기 결과만 빈 리스트, 나머지 정상
  - assemble 시 scan_id/pr_id 정확히 전달
- **완료기준**: 4+ PASS

## Task 10. validation/eval.py
- **입력**: `outputs` (list[AgentOutput])
- **출력**: 채점 리포트
- **Red 테스트**:
  - fixture로 run → expected_output.json과 비교 → recall 1.0 / false_alarm 0.0
  - 가짜 출력에 추가 이슈 → false_positive 증가
  - 가짜 출력에서 이슈 제거 → false_negative 증가
- **완료기준**: 3+ PASS + 실제 fixture에 대해 PASS

## ✅ MVP 완성 기준
- Task 1~10 전부 PASS
- `py main.py` → fixture 입력 → JSON 5 이슈 출력
- `py validation/eval.py` → recall 1.0 / false_alarm 0.0 / PASS
- 각 탐지기의 부정 케이스 테스트 통과

## 🔜 다음 단계 (MVP 이후)
- Task 11. prepare/repo.py (clone)
- Task 12. prepare/sandbox.py (Docker)
- Task 13. persist.py (SQLite + persist_pg GCP)
- Task 14. tracing.py
- Task 15. edge_cases.py + memory_leak.py (heuristic + LLM)
- Task 16. harness.py (LangSmith)
- Task 17. M4 scan_summaries 영구 생성 핸드오프
- Task 18. M6 Dev1/Dev4 실연동
````