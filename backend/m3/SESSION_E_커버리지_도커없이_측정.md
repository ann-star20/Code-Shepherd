# SESSION E — 커버리지: 도커 없이도 측정 (컨테이너 안 fallback) (VS Code 복붙용)

> 목적: 지금 `docker compose`(표준 실행)로 m3를 띄우면, m3가 **컨테이너 안**이라
> 커버리지용 도커 샌드박스를 못 띄워 `FileNotFoundError: 'docker'` → **커버리지 측정이 스킵**된다.
> → 도커가 없으면 **m3 컨테이너 안에서 `pytest --cov`를 직접 실행**하는 fallback을 넣어, 어디서 돌든 커버리지가 나오게.

> 범위: **m3 한 곳** — `test-performance-agent/prepare/sandbox.py`의 `run_sandbox()` + 그 테스트(`tests/test_task12_sandbox.py`). 호출부(app/main.py·gateway·데모)는 안 건드려도 됨(전부 run_sandbox를 거치므로 한 곳만 고치면 전파).

---

## 배경 (왜 이렇게 고치나 — 작업자 필독)

- 커버리지는 `run_sandbox()`가 `docker run ... sh -c "pytest --cov ..."` 로 **격리 샌드박스**를 띄워 측정한다.
- 표준 실행이 `docker compose`라 m3 자신이 **컨테이너 안**에서 돈다 → 그 안엔 `docker` 명령이 없음(이미지에 git만 설치) → 샌드박스 못 띄움 → 호출부가 예외를 삼켜 **커버리지 skip**(로그 `m3.coverage.skip`).
- 도커 안에서 또 도커를 띄우는 것(docker-in-docker)은 소켓 마운트 + 경로 정합 + 보안까지 얽혀 **복잡·취약**. 우리는 **내/팀 레포만** 다루므로 강한 격리가 불필요.
- **현업 CI(GitHub Actions 등)도 깨끗한 환경에서 `pytest --cov`를 "직접" 돌린다** — 즉 이 fallback이 오히려 정석에 가깝다.
- 컨테이너는 모든 팀원 노트북에서 동일 → **한 번 고쳐 dev에 머지하면 팀 전원 커버리지 작동.**

---

```
너는 우리 팀 시니어 백엔드 엔지니어다. 작업 디렉토리: C:\Users\user\Code-Shepherd\backend\m3
테스트는 m3 가상환경 python으로: .venv\Scripts\python.exe -m pytest test-performance-agent/tests/test_task12_sandbox.py -q
(python.exe 는 Store 스텁이라 직접 호출 금지)

[작업 방식]
- tdd-workflow 스킬로 테스트부터(TDD는 항상). 외부 실행(docker/pytest)은 mock 한다 — 실제로 도커나 테스트를 돌리지 않는다.
- 구현 방법은 코드를 읽고 네가 가장 깔끔하게 설계하라(아래는 '무엇/제약'이지 '어떻게'가 아니다).
- 막히면 systematic-debugging / verification-before-completion 스킬 활용 가능.

[배경/문제]
prepare/sandbox.py 의 run_sandbox(work_dir, ...) 는 'docker run ... pytest --cov ...' 로 커버리지를 측정한다.
docker compose 로 띄우면 m3가 컨테이너 안이라 'docker'가 없어 FileNotFoundError → 호출부가 커버리지를 skip 한다.
(호출부: app/main.py, webhook-gateway/agents/dev3_adapter.py 등 — 전부 run_sandbox 를 거친다.)

[목표]
run_sandbox 안에 '도커 없을 때 fallback'을 넣는다:
- 도커가 쓸 수 있으면 → 기존 도커 샌드박스 경로 그대로(격리 유지).
- 도커가 없으면(컨테이너 안 등) → work_dir 에서 같은 테스트 명령(python -m pytest --cov=src --cov-report=json)을
  '직접' 실행하고, 생성된 coverage.json 을 읽어 동일한 반환형({returncode, stdout, coverage})으로 돌려준다.
→ run_sandbox 한 곳만 고치면 모든 호출부가 자동으로 혜택.

[반드시 지킬 것 — 합격 기준]
- 도커가 있을 때 동작/반환형은 기존과 100% 동일(회귀 0).
- 반환 dict 모양({returncode, stdout, coverage})과 coverage dict 구조는 양쪽 경로가 같아야 한다(호출부가 그대로 읽게).
- 가짜 커버리지 금지 — 측정 못 하면 정직하게 coverage=None.
- fallback이 '격리를 약하게 한다'(PR 테스트가 m3 환경에서 직접 돈다)는 트레이드오프를 코드 주석에 명시.
  (내/팀 레포 전용이라 허용. 불특정 외부 PR 서비스가 되면 재검토 — 범위 밖.)
- 합격: docker compose 로 띄운 m3 가 커버리지를 측정한다(더 이상 'docker 없음'으로 skip 안 함, TEST-001/004 탐지).

[TDD]
- 기존 test_task12_sandbox.py 는 prepare.sandbox.subprocess.run 을 mock 한다 — 같은 방식 재사용.
- 신규: 도커 미가용 상황(예: docker 탐지 실패/FileNotFoundError)을 mock → fallback 이 'python -m pytest --cov' 를
  직접 실행하고 coverage 를 반환하는지 검증.
- 회귀: 도커 가용 시 기존 테스트 green 유지.
- 경계(테스트 실패해도 커버리지 회수, deps 설치 필요 레포 등)는 네가 더 생각해서 테스트.

[끝나면]
- [변경 파일 / 테스트 결과 / docker compose 로 m3 띄워 커버리지 실제로 측정되는지(로그 m3.coverage.measured)] 정리.
- 막히면 멈추고 물어봐라.
```

---

## 참고 (사용자용 메모)
- 바뀌는 건 **"커버리지를 어디서 재느냐"** 하나 — 도커가 없으면 **m3 상자 안에서 그냥 직접** 재게. 도커가 있으면 기존대로.
- **`run_sandbox` 한 곳만** 고치면, 그걸 쓰는 모든 데(앱·게이트웨이)가 자동 적용.
- 이거 **dev에 머지하면 → 팀원이 풀 받고 `docker compose up` 하면 → 전원 커버리지 작동.** (컨테이너가 다 똑같으니까)
- 잃는 것: 격리가 약간 약해짐(내/팀 레포만 쓰니 OK). 현업 CI도 이렇게 직접 돌리니 정석에 가까움.
