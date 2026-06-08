# AGENT_STATE_SCHEMA.md — LangGraph 공통 State 스키마

**버전**: v1.0 | **위치**: `src/common/state.py` | **작성일**: 2026-06-04  
**모든 모듈은 이 State 스키마를 기반으로 동작한다. 임의 재정의 금지.**

---

## 1. 전체 State 필드 정의

| 필드 | 타입 | 설명 | 예시 | 사용 모듈 |
|------|------|------|------|-----------|
| `task_id` | `str` | PR 리뷰 단위 고유 ID. UUID v4. | `"550e8400-e29b-41d4-a716"` | M1 생성, M2~M4 읽기 |
| `trace_id` | `str` | LangSmith + DB 추적 ID | `"pr_3a9f1c2b44e0"` | M1 생성, 전 모듈 전달 |
| `request_type` | `RequestType` | 요청 유형 분류 | `"pr_review"` | M1 분류, M1 라우팅 기준 |
| `module_id` | `str` | 현재 처리 중인 모듈 ID | `"module_2"` | 각 모듈이 자신의 ID 기록 |
| `developer` | `DeveloperInfo` | PR 작성자 정보 | (아래 참고) | M1 채움, M4 학습 추천에 사용 |
| `pr_context` | `PRContext \| None` | PR 정보 (PR 리뷰 시에만) | (아래 참고) | M1 채움, M2/M3 읽기 |
| `kms_context` | `KMSContext \| None` | KMS 검색 결과 | (아래 참고) | M1 채움, M2/M3/M4 읽기 |
| `analysis_results` | `List[AgentResult]` | M2/M3 분석 결과 누적 목록 | `[{...}, {...}]` | M2/M3 추가, M4 읽기 |
| `issues` | `List[IssueItem]` | 전체 이슈 목록 (취합) | `[{severity: "Major"...}]` | M2/M3 추가, M4 읽기 |
| `validation_result` | `str \| None` | 현재 단계 검증 결과 | `"pass"` | 각 모듈 채움 |
| `retry_count` | `int` | 현재 단계 재시도 횟수 | `0` | 각 모듈 증가 |
| `status` | `AgentStatus` | 파이프라인 전체 상태 | `"running"` | 각 모듈이 갱신 |
| `next_agent` | `str \| None` | 다음 실행할 모듈/노드 | `"module_4"` | M1/M4 라우팅 기록 |
| `error_message` | `str \| None` | 오류 발생 시 메시지 | `"timeout: 30s"` | 실패 모듈이 채움 |

---

## 2. 서브 모델 정의

### DeveloperInfo

| 필드 | 타입 | 설명 | 예시 |
|------|------|------|------|
| `user_id` | `str` | PostgreSQL `users.id` | `"usr_001"` |
| `github_id` | `str` | GitHub 사용자명 | `"junior_dev_01"` |
| `skill_level` | `SkillLevel` | 개발자 수준 | `"junior"` |
| `tech_stack` | `List[str]` | 사용 기술 스택 | `["python", "fastapi"]` |

### PRContext

| 필드 | 타입 | 설명 | 예시 |
|------|------|------|------|
| `pr_id` | `str` | GitHub PR 번호 | `"42"` |
| `pr_diff` | `str` | unified diff 전체 | `"--- a/auth.py\n+++ b/auth.py\n..."` |
| `repo` | `str` | 레포지토리 전체 경로 | `"org/backend-service"` |
| `author_github_id` | `str` | PR 작성자 GitHub ID | `"junior_dev_01"` |

### KMSContext

| 필드 | 타입 | 설명 | 예시 |
|------|------|------|------|
| `architecture_docs` | `List[str]` | 관련 chunk_id 목록 | `["chunk-001", "chunk-002"]` |
| `coding_conventions` | `str` | 관련 코딩 컨벤션 텍스트 | `"N+1 쿼리 방지: for 루프 안에서..."` |
| `previous_pr_issues` | `List[str]` | 이전 PR에서 발생한 이슈 패턴 | `["N+1 쿼리", "SQL 인젝션"]` |

### IssueItem

| 필드 | 타입 | 설명 | 예시 |
|------|------|------|------|
| `severity` | `Severity` | 심각도 | `"Critical"` |
| `line` | `int` | 발생 라인 번호 | `42` |
| `file` | `str` | 파일 경로 | `"src/auth.py"` |
| `message` | `str` | 이슈 설명 | `"SQL 인젝션 취약점 발견"` |
| `rule_id` | `str` | 규칙 ID | `"SEC-001"` |
| `suggestion` | `str` | 수정 제안 | `"파라미터 바인딩 사용"` |

### IssueSummary

| 필드 | 타입 | 설명 |
|------|------|------|
| `critical` | `int` | Critical 이슈 수 |
| `major` | `int` | Major 이슈 수 |
| `minor` | `int` | Minor 이슈 수 |

### AgentResult (Output Contract)

| 필드 | 타입 | 설명 |
|------|------|------|
| `task_id` | `str` | 작업 단위 ID |
| `trace_id` | `str` | 추적 ID |
| `agent_name` | `str` | 에이전트 이름 |
| `module_id` | `str` | 모듈 ID |
| `status` | `AgentStatus` | 실행 상태 |
| `issues` | `List[IssueItem]` | 발견된 이슈 목록 |
| `summary` | `IssueSummary` | 이슈 집계 |
| `validation_result` | `str` | `"pass \| fail \| skip"` |
| `execution_ms` | `int` | 실행 시간 (밀리초) |
| `next_agent` | `str \| None` | 다음 에이전트 |

---

## 3. Pydantic BaseModel 코드 (`src/common/state.py`)

> 이 파일이 실제 구현 파일이다. 아래 코드를 `src/common/state.py`에 그대로 사용한다.

```python
"""
공통 LangGraph State 스키마 — 모든 모듈이 공유하는 단일 진실의 원천.

모든 모듈은 PlatformState를 기반으로 동작한다.
모듈 전용 필드가 필요하면 PlatformState를 상속하되,
공통 필드는 절대 재정의하지 않는다.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class RequestType(str, Enum):
    PR_REVIEW    = "pr_review"
    KMS_QUERY    = "kms_query"
    ONBOARDING   = "onboarding"
    ARCHITECTURE = "architecture"


class AgentStatus(str, Enum):
    RUNNING      = "running"
    SUCCESS      = "success"
    FAIL         = "fail"
    HITL_PENDING = "hitl_pending"
    ESCALATED    = "escalated"


class SkillLevel(str, Enum):
    JUNIOR = "junior"
    MID    = "mid"
    SENIOR = "senior"


class Severity(str, Enum):
    CRITICAL = "Critical"
    MAJOR    = "Major"
    MINOR    = "Minor"


class ValidationResult(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"


# ---------------------------------------------------------------------------
# 서브 모델
# ---------------------------------------------------------------------------

class DeveloperInfo(BaseModel):
    model_config = ConfigDict(strict=True)

    user_id:      str
    github_id:    str
    skill_level:  SkillLevel
    tech_stack:   list[str] = Field(default_factory=list)


class PRContext(BaseModel):
    model_config = ConfigDict(strict=True)

    pr_id:            str
    pr_diff:          str
    repo:             str
    author_github_id: str


class KMSContext(BaseModel):
    model_config = ConfigDict(strict=True)

    architecture_docs:    list[str] = Field(default_factory=list)
    coding_conventions:   str       = ""
    previous_pr_issues:   list[str] = Field(default_factory=list)


class IssueItem(BaseModel):
    model_config = ConfigDict(strict=True)

    severity:   Severity
    line:       int
    file:       str
    message:    str
    rule_id:    str
    suggestion: str


class IssueSummary(BaseModel):
    model_config = ConfigDict(strict=True)

    critical: int = 0
    major:    int = 0
    minor:    int = 0


class AgentResult(BaseModel):
    """Output Contract — 모든 Agent의 출력이 이 형식을 따른다."""

    model_config = ConfigDict(strict=True)

    task_id:          str
    trace_id:         str
    agent_name:       str
    module_id:        str
    status:           AgentStatus
    issues:           list[IssueItem]    = Field(default_factory=list)
    summary:          IssueSummary       = Field(default_factory=IssueSummary)
    validation_result: ValidationResult  = ValidationResult.SKIP
    execution_ms:     int
    next_agent:       Optional[str]      = None


# ---------------------------------------------------------------------------
# 공통 LangGraph State (TypedDict 형식 — LangGraph 호환)
# ---------------------------------------------------------------------------

from typing import TypedDict


class PlatformState(TypedDict, total=False):
    """
    모든 모듈이 공유하는 LangGraph State.

    total=False: 모든 필드가 optional. 각 모듈은 자신이 담당하는 필드만 채운다.
    Module 1이 초기값을 설정하고, 이후 모듈들이 필드를 추가/갱신한다.

    필드 책임:
        task_id, trace_id, request_type, developer, pr_context, kms_context
            → Module 1 (Orchestrator) 초기화
        analysis_results, issues
            → Module 2/3 (병렬 분석) 추가
        validation_result, retry_count, status, next_agent, error_message
            → 각 모듈이 자신의 처리 결과를 기록
    """

    # Module 1이 초기화
    task_id:      str
    trace_id:     str
    request_type: RequestType
    module_id:    str

    # Module 1이 채움 (요청 파싱)
    developer:   DeveloperInfo
    pr_context:  PRContext            # PR 리뷰 시에만
    kms_context: KMSContext           # KMS 검색 후

    # Module 2/3이 채움 (병렬 분석 결과 누적)
    analysis_results: list[AgentResult]
    issues:           list[IssueItem]

    # 각 모듈이 채움
    validation_result: str            # "pass | fail | skip"
    retry_count:       int
    status:            AgentStatus
    next_agent:        str            # None이면 END
    error_message:     str            # 실패 시


# ---------------------------------------------------------------------------
# 모듈별 State 확장 예시
# ---------------------------------------------------------------------------

class Module2State(PlatformState, total=False):
    """Module 2 전용 추가 필드 (공통 필드 재정의 금지)."""
    static_analysis_raw: str          # ESLint/Pylint 원본 출력
    security_scan_raw:   str          # 보안 스캔 원본 출력


class Module4State(PlatformState, total=False):
    """Module 4 전용 추가 필드."""
    verdict:            str           # "lgtm | rework | escalate"
    comment_body:       str           # GitHub 코멘트 마크다운
    learning_resources: list[dict]    # 학습 자료 목록
    onboarding_update:  dict          # 온보딩 이력 갱신 데이터
```

---

## 4. 모듈별 State 사용 패턴

### Module 1 (Orchestrator) — State 초기화

```python
def initialize_state(webhook_payload: dict, user: DeveloperInfo) -> PlatformState:
    from common.trace import new_pr_trace
    return {
        "task_id":      str(uuid4()),
        "trace_id":     new_pr_trace(),
        "request_type": RequestType.PR_REVIEW,
        "module_id":    "module_1",
        "developer":    user,
        "pr_context":   PRContext(
            pr_id=webhook_payload["number"],
            pr_diff=webhook_payload["diff"],
            repo=webhook_payload["repo"],
            author_github_id=webhook_payload["author"],
        ),
        "analysis_results": [],
        "issues":           [],
        "retry_count":      0,
        "status":           AgentStatus.RUNNING,
    }
```

### Module 2/3 (분석) — State에 결과 추가

```python
def add_analysis_result(state: PlatformState, result: AgentResult) -> dict:
    # LangGraph는 반환 dict의 키만 State에 병합한다
    return {
        "analysis_results": state.get("analysis_results", []) + [result],
        "issues":           state.get("issues", []) + result.issues,
        "module_id":        "module_2",
        "status":           result.status,
    }
```

### Module 4 (Evaluator) — State 읽기 + 판정

```python
def evaluate(state: PlatformState) -> dict:
    results = state.get("analysis_results", [])
    total_critical = sum(r.summary.critical for r in results)
    total_major    = sum(r.summary.major    for r in results)

    if total_critical >= 1:
        verdict = "escalate"
    elif total_major >= 3:
        verdict = "rework"
    else:
        verdict = "lgtm"

    return {
        "verdict":    verdict,
        "module_id":  "module_4",
        "status":     AgentStatus.SUCCESS,
        "next_agent": None,
    }
```

---

## 5. Module 5 — 독립 State

Module 5 (GraphDB + YouTube)는 PlatformState를 사용하지 않는다.  
doc_id / file_hash를 공통 키로 보존하여 향후 KMS 연결 가능하게 설계한다.

```python
class Module5State(TypedDict, total=False):
    """Module 5 전용 독립 State."""
    # 공통 키 (향후 KMS 연결을 위해 필수 보존)
    doc_id:            str           # UUID v4 — 반드시 생성
    file_hash:         str           # SHA-256 — 중복 감지 + KMS 매칭용
    source_system:     str           # 항상 "graph_youtube"
    original_filename: str

    # 처리 결과
    entities:          list[dict]    # 추출된 엔티티
    relations:         list[dict]    # 엔티티 간 관계
    keywords:          list[str]     # 키워드 목록
    recommend_query:   list[str]     # YouTube 검색 쿼리
    youtube_results:   list[dict]    # YouTube 추천 결과

    # 상태
    status:            str           # "stored | failed"
    error_message:     str
```

---

## 6. State 불변 규칙

```
□ PlatformState의 14개 공통 필드는 다른 TypedDict에서 재정의 금지
□ Module 5는 PlatformState를 상속하지 않는다 (독립 State)
□ task_id는 Module 1이 생성, 이후 변경 금지
□ trace_id는 Module 1이 생성, 이후 변경 금지
□ analysis_results는 덮어쓰기 금지 — 항상 기존 목록에 추가 (+= 패턴)
□ status 갱신은 각 모듈의 마지막 반환에서만 수행
```
