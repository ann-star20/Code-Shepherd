# Dev 2: 정적 분석 + 보안 스캔 에이전트 설계서

**프로젝트**: 조직 지식 관리 + 개발자 온보딩 멀티 에이전트 플랫폼
**담당**: Dev 2
**작성일**: 2026-05-22
**MAS 패턴**: Parallel Independent Agents
**하네스**: asyncio.gather (동시 실행)

---

## 1. 역할 요약

PR diff를 받아 **정적 분석(Static Analysis)** 과 **보안 스캔(Security Scan)** 두 에이전트를 병렬 실행하고, 표준 출력 형식으로 Dev4(평가 에이전트)에게 결과를 전달한다.

---

## 2. MAS 패턴: Parallel Independent Agents

```
오케스트레이터 (Dev1)
        │
        ▼
  [Dev2 진입점]
  asyncio.gather()
  ┌─────────────────────────────┐
  │                             │
  ▼                             ▼
[StaticAnalysisAgent]    [SecurityScanAgent]
  - ESLint / Pylint        - SQL Injection 탐지
  - 순환복잡도              - XSS / CSRF 탐지
  - 중복 코드 감지          - 의존성 CVE 스캔
  - 코드 스멜 감지          - OWASP Top10 체크
  │                             │
  └─────────┬───────────────────┘
            ▼
       결과 병합 후 Dev4로 전달
```

두 에이전트는 서로 독립적으로 실행된다. 한 쪽이 느려도 다른 쪽을 기다리지 않으며, 에이전트별 타임아웃은 30초다.

---

## 3. 워크플로우

```
[입력] 오케스트레이터로부터 task payload 수신
  ↓
[파싱] PR diff → 변경된 파일/언어별 분류
  ↓
[병렬 실행] asyncio.gather(
    static_analysis_agent(diff),
    security_scan_agent(diff)
  )
  ↓
  ┌─────────────────────┬────────────────────┐
  │ StaticAnalysis 결과  │  SecurityScan 결과  │
  │ - Pylint/ESLint 실행 │  - Bandit/Semgrep   │
  │ - 복잡도 계산        │  - safety (CVE)     │
  │ - 중복/스멜 감지     │  - OWASP 패턴 매칭  │
  └─────────────────────┴────────────────────┘
  ↓
[결과 병합] 두 결과를 표준 출력 계약 형식으로 직렬화
  ↓
[검증 에이전트 (P1)]
  - 오탐률 추적 에이전트 (이전 결과와 비교)
  - 보안 룰셋 최신화 확인 에이전트
  ↓
[출력] Dev4 평가 에이전트로 JSON 전달
```

---

## 4. 디렉토리 아키텍처

```
dev2/
├── agent.py              # 진입점: asyncio.gather 조율
├── static_analysis/
│   ├── runner.py         # ESLint/Pylint subprocess 실행
│   ├── complexity.py     # 순환복잡도 계산 (radon)
│   ├── duplication.py    # 중복 코드 감지 (CPD)
│   └── smell.py          # 코드 스멜 (함수 길이, 파라미터 수)
├── security_scan/
│   ├── runner.py         # Bandit/Semgrep 실행
│   ├── dependency.py     # safety / pip-audit로 CVE 스캔
│   ├── owasp.py          # OWASP Top10 패턴 매칭
│   └── patterns.py       # SQL Injection, XSS, CSRF 정규식/규칙
├── validators/
│   ├── false_positive.py # 오탐률 추적 에이전트
│   └── ruleset_check.py  # 룰셋 최신화 확인
├── schema.py             # 입출력 Pydantic 모델
└── tests/
    ├── test_static.py
    └── test_security.py
```

---

## 5. 기능 요구사항

| ID | 요구사항 | 우선순위 | 담당 에이전트 |
|----|----------|----------|--------------|
| F-SA-01 | ESLint / Pylint 실행 및 결과 파싱 | P0 | StaticAnalysis |
| F-SA-02 | 순환복잡도 측정 (임계값: 10 이상 시 Major) | P1 | StaticAnalysis |
| F-SA-03 | 중복 코드 감지 | P1 | StaticAnalysis |
| F-SA-04 | 코드 스멜 감지 (너무 긴 함수, 과도한 파라미터) | P2 | StaticAnalysis |
| F-SEC-01 | SQL 인젝션 패턴 탐지 | P0 | SecurityScan |
| F-SEC-02 | XSS / CSRF 취약점 탐지 | P0 | SecurityScan |
| F-SEC-03 | 의존성 CVE 스캔 | P0 | SecurityScan |
| F-SEC-04 | OWASP Top 10 체크리스트 검사 | P1 | SecurityScan |
| F-SA-05 | 결과를 표준 출력 계약 형식으로 반환 | P0 | 공통 |
| 검증 | 오탐(false positive)률 추적 에이전트 | P1 | validators |
| 검증 | 보안 룰셋 최신화 확인 에이전트 | P1 | validators |

---

## 6. 핵심 도구 스택

| 기능 | 도구 | 비고 |
|------|------|------|
| Python 정적 분석 | **Pylint** | F-SA-01 |
| JS/TS 정적 분석 | **ESLint** | F-SA-01, subprocess 실행 |
| 순환복잡도 | **radon** | F-SA-02, CC > 10 → Major |
| 중복 코드 | **CPD** (PMD) | F-SA-03 |
| 보안 스캔 (Python) | **Bandit** | SQL Injection, XSS 등 |
| 보안 스캔 (다중언어) | **Semgrep** | OWASP 룰셋 적용 |
| CVE 의존성 스캔 | **pip-audit / safety** | F-SEC-03 |
| OWASP Top10 | Semgrep OWASP 룰셋 | F-SEC-04 |

> LLM 호출은 최소화한다. Pylint, Bandit, Semgrep 등 검증된 CLI 도구를 우선 사용하고, LLM은 severity 판단이 애매한 케이스에만 선택적으로 호출한다.

---

## 7. Severity 분류 기준

| 조건 | Severity |
|------|----------|
| SQL Injection / XSS / CSRF 탐지 | **Critical** |
| CVE 점수 7.0 이상 | **Critical** |
| 순환복잡도 > 10 | **Major** |
| CVE 점수 4.0 ~ 6.9 | **Major** |
| 코드 스멜 (함수 > 50줄, 파라미터 > 5개) | **Minor** |
| 중복 코드 감지 | **Minor** |

---

## 8. 입출력 계약

### 입력: 오케스트레이터 (Dev1) → Dev2

```json
{
  "task_id": "uuid",
  "pr_id": "github-pr-number",
  "pr_diff": "string (unified diff format)",
  "context": {
    "architecture_docs": ["chunk_id_1", "chunk_id_2"],
    "coding_conventions": "string",
    "previous_pr_issues": ["N+1 쿼리", "SQL 인젝션"]
  },
  "developer": {
    "id": "string",
    "skill_level": "junior | mid | senior",
    "tech_stack": ["python", "fastapi", "postgresql"]
  }
}
```

### 출력: Dev2 → Dev4 (평가 에이전트)

두 에이전트가 각각 아래 형식으로 결과를 반환한다. 총 2개의 JSON 객체가 Dev4로 전달된다.

```json
{
  "agent": "static_analysis | security_scan",
  "task_id": "uuid",
  "issues": [
    {
      "severity": "Critical | Major | Minor",
      "line": 42,
      "file": "src/auth.py",
      "message": "SQL 인젝션 가능성: 사용자 입력이 직접 쿼리에 삽입됨",
      "rule_id": "SEC-001",
      "suggestion": "파라미터화된 쿼리 사용 권장"
    }
  ],
  "summary": { "critical": 1, "major": 3, "minor": 7 },
  "execution_ms": 1200
}
```

---

## 9. 핵심 구현 스케치

### agent.py — 진입점

```python
import asyncio
from static_analysis.runner import run_static_analysis
from security_scan.runner import run_security_scan

async def run_dev2(payload: dict) -> list[dict]:
    results = await asyncio.gather(
        run_static_analysis(payload),
        run_security_scan(payload),
        return_exceptions=True  # 한 쪽 실패해도 나머지 반환
    )
    return [r for r in results if not isinstance(r, Exception)]
```

### static_analysis/runner.py

```python
import subprocess
from complexity import run_radon
from smell import detect_smells

async def run_static_analysis(payload: dict) -> dict:
    diff = payload["pr_diff"]
    files = extract_changed_files(diff)

    pylint_issues = run_pylint(files)
    complexity_issues = run_radon(files)
    smell_issues = detect_smells(files)

    all_issues = pylint_issues + complexity_issues + smell_issues
    return format_output("static_analysis", payload["task_id"], all_issues)

def run_pylint(files: list[str]) -> list[dict]:
    result = subprocess.run(
        ["pylint", "--output-format=json"] + files,
        capture_output=True, text=True, timeout=30
    )
    return parse_pylint_output(result.stdout)
```

### security_scan/runner.py

```python
from dependency import run_pip_audit
from owasp import run_semgrep_owasp

async def run_security_scan(payload: dict) -> dict:
    diff = payload["pr_diff"]
    files = extract_changed_files(diff)

    bandit_issues = run_bandit(files)
    cve_issues = run_pip_audit(payload.get("requirements_file"))
    owasp_issues = run_semgrep_owasp(files)

    all_issues = bandit_issues + cve_issues + owasp_issues
    return format_output("security_scan", payload["task_id"], all_issues)

def run_bandit(files: list[str]) -> list[dict]:
    result = subprocess.run(
        ["bandit", "-r", "-f", "json"] + files,
        capture_output=True, text=True, timeout=30
    )
    return parse_bandit_output(result.stdout)
```

### schema.py — Pydantic 모델

```python
from pydantic import BaseModel
from typing import Literal

class Issue(BaseModel):
    severity: Literal["Critical", "Major", "Minor"]
    line: int
    file: str
    message: str
    rule_id: str
    suggestion: str

class Summary(BaseModel):
    critical: int
    major: int
    minor: int

class AgentOutput(BaseModel):
    agent: Literal["static_analysis", "security_scan"]
    task_id: str
    issues: list[Issue]
    summary: Summary
    execution_ms: int
```

---

## 10. LangSmith 연동

모든 에이전트 호출에 trace를 부여하고 PostgreSQL에 실행 로그를 저장한다.

```python
from langsmith import traceable

@traceable(name="StaticAnalysisAgent")
async def run_static_analysis(payload: dict) -> dict:
    ...

@traceable(name="SecurityScanAgent")
async def run_security_scan(payload: dict) -> dict:
    ...
```

PostgreSQL trace 로그 구조:

```json
{
  "trace_id": "trc_dev2_XXXX",
  "agent_name": "StaticAnalysisAgent | SecurityScanAgent",
  "task_id": "uuid",
  "status": "success | fail | timeout",
  "critical_count": 1,
  "major_count": 3,
  "minor_count": 7,
  "execution_ms": 1200,
  "started_at": "ISO8601",
  "ended_at": "ISO8601",
  "error_message": "if any"
}
```

---

## 11. 개발 우선순위 (주차별)

| 주차 | 목표 | 완료 기준 |
|------|------|-----------|
| Week 1 | schema.py (Pydantic 모델) + mock 출력 서버 | Dev4가 mock 결과 수신 가능 |
| Week 2~3 | P0 구현: Pylint, Bandit, Semgrep, CVE 스캔 | 단위 테스트 통과 |
| Week 4 | 실제 PR diff 파싱 + asyncio.gather 연결 | 실제 diff 입력 → 결과 출력 E2E |
| Week 5 | P1 구현: radon(복잡도), CPD(중복), OWASP | P1 단위 테스트 통과 |
| Week 6 | 검증 에이전트 + 오탐률 추적 + 버그 수정 | 전체 데모 시나리오 동작 |

---

## 12. 비기능 요구사항

| 항목 | 요구사항 |
|------|----------|
| 응답 시간 | 두 에이전트 병렬 기준 30초 이내 완료 |
| 타임아웃 | 에이전트별 30초. 초과 시 해당 결과 제외 후 진행 |
| 오류 격리 | 한 에이전트 실패 시 나머지 결과는 정상 반환 (`return_exceptions=True`) |
| 추적성 | 모든 실행에 trace_id 부여. LangSmith + PostgreSQL 로그 저장 |
| 테스트 | 에이전트 단위 테스트 필수. 취약 코드 샘플로 탐지율 검증 |
