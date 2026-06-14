# m3 탐지기 vendoring 스냅샷 (frozen fork)

**복사일**: 2026-06-12
**출처**: `backend/m3/test-performance-agent/`
**출처 커밋 SHA**: `87b1d1af` (2026-06-08, "fix(m3): /review 500 — contracts 동명 충돌 sys.path 순서 강제")
**브랜치**: `feature/module2-static-security`

---

## 이게 뭔가

m3가 폴더를 재구현할 예정이라 m3 서비스 엔드포인트(`/verify/tests`·`/analyze/performance`)를
client로 호출하면 깨질 수 있다. 그래서 **현재 시점 m3 탐지기 로직을 m2 트리로 복사(포크)**해
m2가 자기 사본을 소유하게 한다. 이후 m3 폴더가 어떻게 바뀌든 m2는 영향받지 않는다.

## 상태

- **스냅샷 고정만 완료** — 아직 m2 오케스트레이터에 **연결(와이어링)되지 않음**.
- 연결은 `m2_orchestrator_plan.md` Phase 2에서 수행.
- 이 디렉토리는 **sys.path 루트로 사용**하는 구조(m3 원본과 동일). 최상위에 `__init__.py`를
  두지 않고, 내부 모듈은 `from contracts import ...`, `from performance import ...` 식 top-level import 유지.

## 복사 범위

포함: `contracts.py main.py harness.py tracing.py persist.py`
      `assemble/ config/ conventions/ enrich/ filter/ performance/ prepare/ rag/ test_verification/ validation/`
제외: `tests/ docs/ demo_showcase.py showcase_issues.json __pycache__/`

## Phase 2 연결 시 주의 (요약)

- **동명 충돌**: m2 `app/contract.py` ↔ vendored `contracts.py` → 네임스페이스/sys.path 격리 필요.
- **가벼운 것부터**: `performance/complexity`·`performance/nplus1`은 Docker 불필요.
  `test_verification/coverage`는 Docker 샌드박스 필요 → 최후·선택.
- **repo_path**: m2 `analyzer.py`의 `_materialize`(diff→파일 복원) 재사용으로 git clone 회피 검토.
- **의존성**: 실제 사용하는 탐지기가 요구하는 패키지만 `m2/pyproject.toml`에 추가.

> 원본을 되살리려면: `git show 87b1d1af:backend/m3/test-performance-agent/<path>`
