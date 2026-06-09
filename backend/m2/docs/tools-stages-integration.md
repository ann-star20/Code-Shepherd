# [다음 작업] M2 도구 상태 · 파이프라인 단계 trace 연동 (작업 B)

> 프론트(정적분석·보안 스캔 페이지)에 **스캔 도구 실행/스킵 상태**와 **파이프라인 노드별 진행 상태**를
> 실데이터로 표시하기 위한 백엔드 연동 작업. 현재는 프론트에서 optional 필드로 두어 자동 숨김/폴백 중.

## 현재 상태 (작업 A 완료)
- 프론트 `frontend/src/pages/security/SecurityPage.tsx` — 더미 제거, 실연결 완료.
- 이슈/KPI/탭/테이블은 m3 `/review` 응답으로 실데이터 동작.
- **미제공 필드** (이번 작업 대상):
  - `tools` — 도구별 실행/스킵 + 사유 (Pylint/Radon/ESLint/Bandit/Semgrep)
  - `stages` — 파이프라인 노드별 status·소요시간 (run_tools → vector_search → llm_judge → store)
- 프론트는 이미 다음을 optional로 수신하도록 준비됨:
  - `ReviewResult.tools?: ToolStatus[]` → 좌측 "스캔 도구" 카드
  - `M2PipelineFlow`의 `stages?: M2StageTrace[]` props → 노드별 상태 표시

## 데이터 흐름
```
m1 ──POST /analyze/static|security──▶ m2
m1 ◀──M2AnalyzeResponse────────────── m2     # m1이 shared 계약으로 파싱
m1 ──▶ m3 집계 ──▶ review_results 저장
프론트 ◀── m3 GET /review/{owner}/{repo}/{pr}
```
- m1 호출부: `backend/m1/app/clients/module_clients.py`
  (`call_m2_analyze_static`, `call_m2_analyze_security` → `M2AnalyzeResponse(**resp.json())`)
- 공유 계약: `backend/_shared/shared/contracts.py` (`M2AnalyzeResponse`, `IssueItem` 등)
- m3 저장/조회: `backend/m3/test-performance-agent/persist.py`, 엔드포인트 `backend/m3/app/main.py` (`GET /review/...`)

## 변경 체크리스트

### 1. 공유 계약 — `backend/_shared/shared/contracts.py` (m2 담당, 단독 가능)
`M2AnalyzeResponse`에 필드 추가. 새 필드라 m1은 자동 수신(Pydantic), 깨지지 않음.
```python
class ToolStatus(BaseModel):
    name: str                                   # "Pylint" | "Radon" | "ESLint" | "Bandit" | "Semgrep"
    kind: Literal["static", "security"]
    status: Literal["ran", "skipped"]
    reason: str | None = None                   # 스킵 사유 ("Python 파일 없음", "Windows 미지원" 등)
    issue_count: int = 0

class StageTrace(BaseModel):
    key: Literal["run_tools", "vector_search", "llm_judge", "store"]
    status: Literal["pending", "running", "success", "fail"]
    ms: int | None = None

class M2AnalyzeResponse(BaseModel):
    # ...기존 필드...
    tools: list[ToolStatus] = Field(default_factory=list)
    stages: list[StageTrace] = Field(default_factory=list)
```

### 2. m2 분석기 — `backend/m2/app/analyzer.py` (m2 담당)
- 각 도구 호출 지점에서 실행/스킵 여부 + 사유 기록 → `tools` 채우기.
- 파이프라인 단계별 시작/종료 시각·성공/실패 기록 → `stages` 채우기.
- 응답(`main.py`)에서 `M2AnalyzeResponse`에 함께 반환.

### 3. m1 전달 — (m1 담당과 협의)
- `module_clients.py`는 이미 전체 응답을 파싱하므로 수신은 자동.
- m1이 m2 응답을 m3로 넘길 때 `tools`/`stages`도 함께 전달하도록 확인/수정.
- ⚠️ static + security 두 번 호출하므로 `tools`는 합치고, `stages`는 어느 쪽 기준으로 표시할지 정책 결정 필요.

### 4. m3 저장·조회 — (m3 담당과 협의)
- `review_results` 스키마(`persist.py`)에 `tools`/`stages` JSON 컬럼 추가 (또는 기존 JSON에 포함).
- `GET /review/...` 응답에 `tools`/`stages` 포함하도록 수정.

### 5. 프론트 — 거의 수정 없음
- `ReviewResult`에 `stages?` 받아 `M2PipelineFlow`에 전달만 연결하면 됨 (현재 `tools`는 이미 연결, `stages`는 prop 자리만 있음).

## 분할 전략
- **선행(단독)**: 1 + 2 — 계약에 필드 추가하고 m2가 채움. 이 시점엔 m1/m3가 안 흘려보내므로 프론트엔 아직 안 보임(폴백 유지).
- **후행(협의)**: 3 + 4 + 5 — m1·m3 전달/저장 연결 후 프론트에 실표시.

## 미결정 사항
- security 스캔에도 vector_search/llm_judge 단계가 동일하게 있는지 (static과 stage 구성 차이) → m2 파이프라인 실제 단계 확인 필요.
- static/security 두 응답의 `stages`를 프론트에서 어떻게 합쳐 보여줄지.
