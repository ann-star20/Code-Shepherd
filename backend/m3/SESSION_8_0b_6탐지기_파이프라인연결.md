# SESSION 8-0b — 6탐지기 전체를 파이프라인에 연결 (VS Code 복붙용)

> **시스템 완성 3단계 중 2번째.** 선행: 8-0a(LLM 복구) 완료. 후행: 8-0c·8A~8E.
> 목적: 코드는 구현돼 있는데 메인 파이프라인에 안 꽂혀 있는 TEST-003(엣지케이스)·PERF-003(메모리누수)를 `main.run()`에 연결해 **탐지기 6개 전체**가 PR마다 돌게 한다.
> 범위: `test-performance-agent/main.py`(연결) + edge_cases·memory_leak 두 소스의 주석 정정. **평가(eval.py·골든라벨)는 안 건드린다 — 그건 8B.**
> 선행: **8-0a 완료**(두 탐지기가 LLM 기반이라 LLM이 살아 있어야 제대로 동작).

## 배경 (왜)
- 탐지기 6개 중 **4개만 연결**돼 있다. TEST-003·PERF-003은 구현돼 있는데도 `main.run()`에 없다.
  소스 주석: `★ main.run()에는 연결 안 함 (eval 골든 라벨 보호)`.
- 만든 탐지기를 안 쓰는 건 말이 안 되고, 나중에 연결하면 **8B 골든라벨을 6탐지기 기준으로 다시** 잡아야 한다(이중작업). → **8B보다 먼저 연결.**
- 두 탐지기 시그니처는 기존 4개와 **동일**: `detect(repo_path, changed) -> list[Issue]`. 연결은 같은 try/except → filter_issues 패턴.

---

```
너는 우리 팀 백엔드 엔지니어다. 작업 디렉토리: C:\Users\user\Code-Shepherd\backend\m3\test-performance-agent
실행 환경: docker compose 의 m3 컨테이너(uv). 테스트는 컨테이너 안에서 uv run --extra test pytest.

[작업 방식]
- TDD로(테스트 먼저). superpowers:test-driven-development 스킬 사용.
- 변경은 최소(surgical). 기존 4개 탐지기 호출 패턴(try/except → filter_issues)을 그대로 따른다.
- 평가·골든라벨·성능벤치는 건드리지 않는다(8B/8A 몫).

[선행 점검]
- 8-0a(LLM 복구) 가 끝나 refine/탐지기가 LLM 모드로 도는지 확인(폴백이면 8-0a 먼저).
- 기존 테스트 green: 6개 탐지기 단위테스트 포함
  (test_task4~7, test_task15a_edge_cases, test_task15b_memory_leak, test_task9_main).
- edge_cases.detect / memory_leak.detect 단독 호출 스모크 1회(정상 동작 확인).
  깨져 있으면 멈추고 보고(깨진 탐지기를 파이프라인에 꽂지 말 것).

[목표 — main.run() 에 2개 탐지기 연결]
- edge_cases.detect(repo_path, changed) → test_issues 쪽,
  memory_leak.detect(repo_path, changed) → perf_issues 쪽 으로,
  기존 4개와 동일한 try/except → filter_issues 패턴으로 추가.
  (현재 main.py: cov+missing_funcs → test_issues / nplus1+complexity → perf_issues. 여기에 한 줄씩 더.)
- 두 소스의 `★ main.run()에는 연결 안 함 ...` 주석 + docstring "골든 4" 표현을 "탐지기 6개"로 정정.
- 부분 실패 허용 유지: 한 탐지기가 예외여도 나머지는 정상 산출.

[결정 — 결정성(determinism) 택일하고 기록만]
- TEST-003·PERF-003 은 LLM 모드면 비결정적(같은 PR이라도 출력 흔들림 가능).
- 메인 파이프라인은 "같은 PR=같은 결과"가 신뢰의 핵심 → 택일:
  (a) 메인 경로는 휴리스틱(결정적), LLM은 보강/교차검증으로만, 또는
  (b) LLM 모드를 메인에 두되 비결정성 인정.
  → 어느 쪽이든 한 줄 사유를 코드 주석/리포트에 기록. (발표 MD 문구는 나중 일괄수정 — 여기선 기록만.)

[반드시 지킬 것 — 합격 기준]
- 스모크 1회: 6개 탐지기가 각자 동작(해당 패턴 있으면 이슈 산출)하는 걸 로그로 확인.
- 기존 테스트 전부 여전히 green(회귀 0). 새 연결 분은 테스트로 못박음.
- eval.py·골든라벨은 수정 금지(8B 몫). 정직성: 가짜 이슈 금지.

[TDD]
- test_task9_main(또는 신규): 6개 탐지기가 모두 호출되고 결과가 test_verification/performance 출력에 합쳐진다.
- 한 탐지기 예외 → 나머지 정상(부분 실패 허용) 검증.

[끝나면 — 8-0c / 8A·8B 로 인수인계]
- [연결한 2탐지기 / 결정성 택일·사유 / 6탐지기 스모크 결과 / 회귀 테스트] 정리.
- 다운스트림: 8A 6탐지기 기준 시간 재측정, 8B 골든라벨 6탐지기 기준,
  발표자료 §2-3 데모숫자·§2-4 카탈로그·§5-1 다이어그램 6탐지기로 갱신(MD 마무리 때).
- 막히면 멈추고 물어봐라.
```

---

## 참고 (사용자용 메모)
- 3단계 중 **2번째·제일 무거움**. 이게 8B(탐지 정확도 평가)의 가장 중요한 선행 — 6탐지기로 연결해야 골든라벨을 한 번에 제대로 잡아요.
- "왜 안 연결했었나": 소스 주석에 "골든 라벨 보호"라고 박혀 있어요. 4개 기준 정답을 안 깨려 막아둔 건데, 만든 탐지기를 써야 하니 8B 전에 연결하는 거예요.
