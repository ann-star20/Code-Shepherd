# Claude Code 작업 프롬프트 — m2 내부 mini-orchestrator 추가

## 최우선 제약

1. 팀원들과 공유하는 문서는 절대 수정하지 마라.
   - `docs/` 아래 공통 문서 수정 금지
   - 공통 `MODULE_CONTRACT.md` 수정 금지
   - `GLOBAL_AGENT_RULE.md` 수정 금지
   - 팀 전체 계약 문서, 공통 설계 문서, 공통 스키마 문서 수정 금지
   - 문서 수정이 필요해 보이면 실제 수정하지 말고, 최종 작업 요약에 “문서 반영 필요 사항”으로만 적어라.

2. 기존 m2 정적분석/보안분석 기능은 최대한 살려라.
   - 기존 `/analyze/static` 엔드포인트 삭제 금지
   - 기존 `/analyze/security` 엔드포인트 삭제 금지
   - 기존 `analyzer.py` 로직을 대규모로 갈아엎지 마라
   - 기존 `AgentResult` 응답 계약을 깨지 마라
   - 기존 `rule_id`, `severity`, `summary`, `execution_ms` 구조를 유지해라
   - 기존 테스트가 깨지지 않게 해라
   - 기존 정적분석/보안분석은 “재작성”이 아니라 “재사용”하는 방향으로 구현해라.

---

## 작업 목표

전체 구현 설계가 변경되었다.

기존에는 `m1`이 중앙 오케스트레이터로 `m2`, `m3`를 호출하고 결과를 `m4`에 전달하는 구조였다.

이제는 각 모듈이 자기 영역 안에서 end-to-end 흐름을 자체 구현하는 구조로 변경한다.

이번 작업 대상은 `backend/m2`이다.

핵심 목표는 `m2` 안에 m2 전용 `mini-orchestrator`를 추가하는 것이다.

이 mini-orchestrator는 기존 `m1`의 일부 역할을 `m2` 내부에서 수행한다.

단, 기존 m2 정적분석/보안분석 구현은 최대한 그대로 유지한다. 새 기능은 기존 코드 위에 얹는 방식으로 추가한다.

---

## m2 내부에서 구현할 흐름

1. PR diff를 입력받는다.
2. PR diff를 보고 정적분석/보안분석이 필요한지 판단한다.
3. 분석이 필요하면 기존 m2의 `static_analysis` / `security_scan` 기능을 그대로 재사용한다.
4. `m0`와 `KMS`는 기존 중앙 `m1`을 통해 연결하지 않는다.
5. m2 내부 mini-orchestrator가 직접 `m0`와 `KMS`를 호출할 수 있는 구조로 만든다.
6. KMS에서 코딩 컨벤션, 보안 규칙, 이전 PR 이슈, 아키텍처 문서 같은 context를 가져올 수 있게 한다.
7. m2 분석 결과와 context를 조합해서 `m4`에 전달한다.
8. `m4`의 리뷰 생성 결과를 받아 최종 응답으로 반환한다.

---

## 중요한 설계 원칙

- 기존 `/health`, `/analyze/static`, `/analyze/security`는 반드시 유지한다.
- `analyzer.py`는 분석 도구 실행만 담당하게 유지한다.
- `analyzer.py` 안에 `m0`, `KMS`, `m4` 호출 로직을 넣지 않는다.
- orchestration 책임은 새 `orchestrator.py`에 둔다.
- `m0` / `KMS` / `m4` 호출은 `clients` 계층으로 분리한다.
- 기존 구현을 건드려야 한다면 최소 수정만 한다.
- 기존 정적분석/보안분석의 동작 결과가 바뀌지 않게 한다.
- m2는 더 이상 단순 분석기만이 아니라 “정적분석/보안분석 도메인의 end-to-end agent” 역할을 추가로 갖는다.
- m3도 별도로 같은 방식의 m3 전용 end-to-end 구조를 구현할 예정이므로, m2 코드가 m3에 의존하지 않게 한다.
- 기존 `AgentResult` 계약은 깨지지 않게 유지한다.
- 공유 문서 수정 없이 코드와 m2 내부 신규 파일 중심으로 작업한다.

---

## 새로 만들 파일

```text
backend/m2/app/orchestrator.py
backend/m2/app/decision.py
backend/m2/app/clients/m0_client.py
backend/m2/app/clients/kms_client.py
backend/m2/app/clients/m4_client.py
backend/m2/app/services/context_builder.py
backend/m2/app/services/result_mapper.py
```

---

## 수정 가능한 파일

```text
backend/m2/app/main.py
backend/m2/app/contract.py
```

수정 시 주의:

- `main.py`는 새 엔드포인트 추가 목적의 최소 수정만 한다.
- `contract.py`는 새 Orchestrate DTO 추가 목적의 최소 수정만 한다.
- `analyzer.py`는 가능하면 수정하지 말고 기존 함수를 호출해서 재사용한다.
- `analyzer.py` 수정이 꼭 필요하면 이유를 작업 결과에 명확히 적고 최소 범위만 수정한다.

---

## 절대 수정하지 말 파일

```text
docs/
공통 MODULE_CONTRACT.md
docs/GLOBAL_AGENT_RULE.md
팀 공통 계약 문서
팀 공통 설계 문서
m1 코드
m3 코드
m4 코드
```

`backend/_shared/shared/contracts.py`는 가능하면 수정하지 마라. 꼭 필요해 보이면 먼저 이유를 설명하고 최소 수정만 제안하라. 실제 수정은 하지 마라.

---

## 새 엔드포인트 추가

```http
POST /orchestrate/review
```

이 엔드포인트의 역할:

- PR diff를 받아 m2 내부 end-to-end 흐름을 실행한다.
- `decision.py`로 분석 필요 여부를 판단한다.
- 필요한 경우 기존 `analyzer.py`를 사용해 `static_analysis` / `security_scan`을 실행한다.
- `m0` / `KMS` context를 붙일 수 있는 구조를 만든다.
- m2 결과를 m4 요청 형식으로 변환한다.
- m4에 전달하고 m4 응답을 포함해 최종 반환한다.

---

## 입력 DTO 예시

```python
class M2OrchestrateRequest(BaseModel):
    task_id: str
    pr_id: str
    pr_diff: str
    owner: str | None = None
    repo: str | None = None
    developer_id: str | None = None
    trace_id: str | None = None
```

---

## 출력 DTO 예시

```python
class M2OrchestrateResponse(BaseModel):
    task_id: str
    pr_id: str
    trace_id: str | None = None
    module_id: str = "module_2"
    status: Literal["success", "fail", "skip"]
    decision: dict
    context: dict | None = None
    static_analysis: AgentResult | None = None
    security_scan: AgentResult | None = None
    m4_review: dict | None = None
    error_message: str | None = None
```

---

## decision.py 구현 기준

- `.py`, `.js`, `.jsx`, `.ts`, `.tsx` 파일 변경이 있으면 `static_analysis` 필요
- 아래 키워드가 diff에 있으면 `security_scan` 필요

```text
auth
login
password
token
secret
jwt
sql
query
subprocess
eval
exec
os.system
```

- 아래 의존성 파일이 바뀌면 `security_scan` 필요

```text
requirements.txt
pyproject.toml
package.json
package-lock.json
poetry.lock
```

- `README`, `docs`, `.md` 파일만 바뀌었으면 skip 가능
- 판단 결과에는 아래 필드를 포함한다.

```json
{
  "needs_static_analysis": true,
  "needs_security_scan": true,
  "reason": "Python files changed and security keyword detected"
}
```

---

## clients 구현 기준

### m0_client.py

- m0 호출용 클라이언트 구조를 만든다.
- 실제 URL은 환경변수 `M0_BASE_URL` 사용.
- 환경변수가 없으면 전체 실패 없이 graceful fallback 한다.

### kms_client.py

- KMS 호출용 클라이언트 구조를 만든다.
- 실제 URL은 환경변수 `KMS_BASE_URL` 사용.
- 코딩 컨벤션, 보안 규칙, 이전 PR 이슈, 아키텍처 문서를 가져올 수 있는 구조로 만든다.
- 환경변수가 없으면 전체 실패 없이 graceful fallback 한다.

### m4_client.py

- m4 호출용 클라이언트 구조를 만든다.
- 실제 URL은 환경변수 `M4_BASE_URL` 사용.
- 환경변수가 없으면 전체 실패 없이 graceful fallback 또는 stub response를 반환한다.

공통 기준:

- 외부 연결 실패 때문에 기존 m2 분석 자체가 중단되지 않게 한다.
- `error_message` 또는 `warnings`에는 어떤 외부 연결이 스킵되었는지 남긴다.

---

## orchestrator.py 구현 기준

`run_m2_orchestration(payload: M2OrchestrateRequest)` 함수를 만든다.

내부 순서:

1. decision 판단
2. skip이면 분석 없이 `status="skip"` 반환
3. m0 context 조회 시도
4. KMS context 조회 시도
5. `static_analysis` 필요 시 기존 analyzer 호출
6. `security_scan` 필요 시 기존 analyzer 호출
7. `result_mapper`로 m4 요청 payload 생성
8. `m4_client`로 m4 호출
9. 최종 `M2OrchestrateResponse` 반환

주의:

- 외부 서비스 호출 실패 때문에 기존 m2 분석 자체가 중단되지 않게 한다.
- m4 호출 실패 시에도 `static_analysis` / `security_scan` 결과는 응답에 포함한다.
- `status` Literal 값이 제한되어 있으면 `status="fail"`과 `error_message`를 사용한다.

---

## main.py 수정 기준

- 기존 `/health`, `/analyze/static`, `/analyze/security`는 유지한다.
- 새 `POST /orchestrate/review`만 추가한다.
- 새 엔드포인트는 `orchestrator.run_m2_orchestration`을 호출한다.

---

## 문서 관련 기준

- 공유 문서는 수정하지 않는다.
- 문서 변경이 필요해 보이면 실제 파일을 수정하지 말고, 최종 요약에 “문서 반영 필요 사항”으로만 적는다.
- 팀원 합의 전에는 공통 문서와 공통 계약 파일을 건드리지 않는다.

---

## 테스트 추가

다음 테스트를 추가한다.

1. PR diff에 Python 파일이 있으면 `static_analysis`가 true인지 테스트
2. 보안 키워드가 있으면 `security_scan`이 true인지 테스트
3. `docs` / `README` / `.md`만 있으면 skip 되는지 테스트
4. `/orchestrate/review`가 기존 analyzer를 호출하고 응답을 반환하는지 테스트
5. `M0_BASE_URL`, `KMS_BASE_URL`, `M4_BASE_URL` 환경변수가 없어도 graceful fallback 되는지 테스트
6. 기존 `/analyze/static`, `/analyze/security` 테스트가 계속 통과하는지 확인

---

## 최종 산출 요약에 반드시 포함할 것

1. 변경된 파일 목록
2. 새로 추가된 파일 목록
3. 기존 정적분석/보안분석 기능을 어떻게 보존했는지
4. 새 실행 흐름 요약
5. 새 엔드포인트 사용 예시 curl
6. 기존 계약과 깨지는 부분이 있는지 여부
7. 공유 문서를 수정하지 않았는지 여부
8. 아직 stub/planned 상태인 부분
9. 문서 반영 필요 사항이 있다면 실제 수정하지 말고 제안만 적기

---

## 마지막 주의 문장

공유 문서 수정은 이번 작업 범위가 아니다. 코드 변경만 하고, 문서 변경 필요사항은 요약으로만 보고해라.

대규모 리팩토링보다 현재 작동 중인 m2 분석 기능을 보존하면서 orchestrator 계층만 점진적으로 추가해라.
