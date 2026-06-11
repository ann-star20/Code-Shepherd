# coverage.json 생성·테스트·Docker 구조 정리

> `test_verification/coverage.py`의 `measure()`가 읽는 `coverage.json`이
> **어떻게 생성되고, 어디서 테스트하며, Docker로 어떻게 띄우는지** 추적한 결과.

---

## 1. coverage.json은 어떻게 생성되나

생성 코드는 [`prepare/sandbox.py`](prepare/sandbox.py)의 `run_sandbox()` 함수다. 흐름:

1. **Docker 컨테이너**를 띄워서 그 안에서 pytest 실행 (`sandbox.py:66-77`):
   ```
   docker run --rm --network none/bridge --memory 512m --cpus 1
     -v {work_dir}:/work -w /work dev3-sandbox
     sh -c "rm -f /work/coverage.json && python -m pytest --cov=src --cov-report=json && coverage json -o /dev/stdout"
   ```
2. 컨테이너 안에서 `pytest-cov`가 커버리지를 측정하고,
   `coverage json -o /dev/stdout`으로 JSON을 **표준출력**에 출력.
3. 호스트(Python)는 stdout에서 `@@@DEV3COVJSON@@@` 마커 뒤의 JSON을
   `_extract_coverage()`로 파싱 (`sandbox.py:140-158`).
4. 그 dict를 **호스트가 직접** `{repo_path}/coverage.json`에 기록 (`sandbox.py:82-99`).

### 왜 이렇게 복잡한가 (stdout 마커 우회)
컨테이너(root)가 bind-mount에 직접 쓴 `coverage.json`을 **Windows 호스트가 권한 문제로 못 읽는 함정**이 있어서,
stdout 마커로 우회한 뒤 호스트가 직접 파일을 쓴다. (`DEV3_TECH_SPEC.md` §9.2, line 537)

### measure()는 생성하지 않고 "읽기만" 한다
[`test_verification/coverage.py`](test_verification/coverage.py)의 `measure()`는
이미 만들어진 `{repo_path}/coverage.json`을 파싱해 메트릭/이슈를 산출하는 **소비자**다.
파일이 없거나 `num_statements=0`이면 `([], None)` 반환 (정직성 원칙).

---

## 2. Docker로 띄우는 게 맞나 — 부분적으로 "예", 단 주의점 2가지

- **이미지**: `dev3-sandbox` (`config/settings.py:35`, `SANDBOX_IMAGE`).
  그러나 **이 레포에 Dockerfile이 없다** (`find` 결과 0건). 이미지는 외부에서 빌드돼 있어야 함.
- **중요 — 현재 메인 파이프라인에 미배선**:
  [`main.py`](main.py)의 `run()`은 `run_sandbox()`를 **호출하지 않는다**.
  바로 `coverage.measure(repo_path)`로 기존 `coverage.json`을 읽을 뿐이다.
  즉 `run_sandbox`는 작성·테스트는 됐지만 메인 파이프라인엔 아직 연결되지 않았다.
  (TECH_SPEC의 `run(use_sandbox=True)` 설계가 코드엔 미반영)

---

## 3. 어디서 테스트하고, 어디서 확인하나

| 대상 | 테스트 파일 | 방식 |
|------|------------|------|
| `coverage.measure()` (파싱/메트릭) | `tests/test_task4_coverage.py` | tmp_path에 가짜 `coverage.json` 써놓고 검증 |
| `run_sandbox()` (도커 래퍼) | `tests/test_task12_sandbox.py` | **`subprocess.run`을 mock** — 실제 도커 안 띄움 |

**핵심**: 테스트들은 실제 Docker를 띄우지 않는다.
- `test_task12_sandbox.py`는 `subprocess.run`을 `MagicMock`으로 막아
  "docker 명령이 올바르게 조립되는지"만 검사.
- `coverage.measure` 테스트는 손으로 만든 fixture JSON을 사용.

**실제 coverage.json 예시 확인**:
`tests/fixtures/sample_repo/coverage.json` — 데모용으로 미리 만들어둔 파일.
`python main.py`를 돌리면 이 fixture 레포를 repo_path로 사용 (`main.py:93`).

---

## 요약

진짜 `coverage.json`은 **도커 안 pytest-cov가 만들고 stdout 마커로 회수해 호스트가 기록**
(`prepare/sandbox.py`). 하지만

1. Dockerfile이 레포에 없고
2. `run_sandbox`가 `main.py`에 아직 연결 안 됨

→ 현재 실동작은 **미리 준비된 fixture `coverage.json`을 읽는 방식**이다.
테스트는 전부 도커를 mock 처리해서 실제 컨테이너 없이 돌아간다.

### 직접 돌려보기
```bash
python main.py                          # fixture 기반 전체 파이프라인
pytest tests/test_task12_sandbox.py     # 샌드박스 래퍼 단위 테스트
pytest tests/test_task4_coverage.py     # coverage 파싱 단위 테스트
```

실제 도커 실측을 붙이려면: **Dockerfile 작성 + `main.py`에서 `run_sandbox` 호출 배선**이 필요하다.
