# 다음 작업 인계 문서 (m2)

> 브랜치: `feature/module2-static-security` | 최종 갱신: 2026-06-13

---

## 0. 한 줄 요약

m2 mini-orchestrator(`app/orchestrator.py`)에
**(1) KMS에서 `context` 채우기** + **(2) `context`를 쓰는 LLM-judge 레이어**를 추가한다.
둘 다 **graceful**(외부 실패가 분석을 막지 않음), **m2 쪽만** 구현(m0 무수정).

- KMS 검색 범위: **m2만 구현 + graceful** (사용자 확정)
- analyzer 활용 깊이: **본격 LLM-judge** (경량 결정적 태깅 아님, 사용자 확정)

---

## 1. 배경 / 핵심 결정 사항

- **오케스트레이터 = m2 mini-orchestrator** (m1 라우팅은 레거시, 사용 안 함 — 사용자 확정).
  - 진입점: `POST /orchestrate/review` → `run_m2_orchestration(req)`.
  - 흐름: `decision.decide` → `run_single_agent`(static/security) → `result_persist` → `result_mapper.build_m4_request` → `m4_client.evaluate` → 응답.
- **`context`(AnalysisContext)란**: 분석 품질을 높이는 보조 입력.
  - `architecture_docs: list[str]` (관련 아키텍처 청크/문서)
  - `coding_conventions: str` (사내 컨벤션)
  - `previous_pr_issues: list[str]` (과거 반복 이슈, 예: "N+1 쿼리")
  - **현재 app/ analyzer는 `pr_diff`만 사용**, context는 받기만 하고 무시.
- **현재 app/ analyzer는 순수 도구 기반** (pylint/radon/bandit/semgrep/eslint subprocess). **LLM 없음** → context를 "활용"하려면 LLM-judge 레이어가 필요.

### ⚠️ 블로커 (Part 1)
- **m0(KMS)에는 검색 엔드포인트가 없다.** `backend/m0/app/main.py`는 `/health` + `/ingest`만 존재. `/search` 미구현.
- m0는 내 모듈 아님 → **수정 금지.**
- 해결책: m2 쪽에서 **합의된 계약**(`KmsSearchRequest/Response`)으로 POST `{M0_URL}/search` 호출하되, **404/연결 실패/미설정 시 graceful**하게 빈 context로 진행. m0 담당자가 `/search` 구현하면 그대로 동작(코드 변경 0).
- `M0_URL=http://m0:8002` 는 `backend/m2/.env.example`에 이미 존재.

---

## 2. Part 1 — KMS context 채우기 (작고 격리됨, graceful)

목표: orchestrate 시작 시 `req.context`가 비어 있으면 KMS에서 채운 뒤 분석.

### 작업 목록
1. **계약 추가** — `backend/_shared/shared/contracts.py` (additive, ~15줄)
   ```python
   class KmsSearchRequest(BaseModel):
       query: str                       # pr_diff 요약 또는 파일 경로 기반 질의
       top_k: int = 3
       trace_id: str | None = None

   class KmsSearchResult(BaseModel):
       chunk_id: str
       content: str
       score: float = 0.0

   class KmsSearchResponse(BaseModel):
       results: list[KmsSearchResult] = Field(default_factory=list)
   ```
   - ⚠️ `backend/_shared/contracts.py` **중복본** 존재 — 동기화 필요한지 먼저 확인.
2. **클라이언트** — `app/clients/kms_client.py` 신규 (~35줄, `m4_client.py` 패턴 그대로)
   - `async def search(req: KmsSearchRequest) -> KmsSearchResponse | None`
   - `_base_url()`: `M0_URL` 또는 `M0_BASE_URL` 읽기, 없으면 None 반환(스킵).
   - httpx POST `{M0_URL}/search`, timeout ~10s, 실패/404 시 `None` (graceful).
3. **오케스트레이터 연결** — `app/orchestrator.py` `run_m2_orchestration` (~12줄)
   - 분석 전에: `if context가 비어있음: kms_resp = await kms_client.search(...)` → 결과를 `req.context.architecture_docs`/`coding_conventions`/`previous_pr_issues`에 매핑.
   - 질의(query)는 `req.pr_diff` 요약(첫 N줄/변경 파일 경로)으로 구성.
4. **응답 필드** — `app/contract.py` `M2OrchestrateResponse`에 `kms_used: bool = False` 추가, 채웠으면 True.
5. **테스트** — kms_client mock으로 (a) 정상 채움 (b) None일 때 빈 context로 진행 두 경로.

> Part 1만 먼저 머지 가능(격리·무해). m0 `/search` 없어도 no-op으로 안전.

---

## 3. Part 2 — LLM-judge 레이어 (큰 작업)

목표: context(architecture_docs/coding_conventions/previous_pr_issues)를 활용해
도구가 뽑은 issue의 severity/suggestion을 LLM이 재판단·보강.

### 청사진 (그대로 따라 미러링)
- **`backend/m2/dev2/nodes/llm_judge.py`** ← 참조 원본. 핵심 패턴:
  - `from langchain_anthropic import ChatAnthropic`, `from langchain_core.messages import HumanMessage`
  - `MODEL_ROUTING = {"Critical": "claude-sonnet-4-6", "Major": "claude-haiku-4-5-20251001", "Minor": None}` (Minor는 LLM 스킵)
  - `LLM_TIMEOUT_SEC = 30.0`, `_llm_cache` 모델 캐시
  - `use_mock = os.getenv("USE_MOCK_LLM", "true").lower() == "true"` → `_get_mock_response()` 경로
  - `_extract_json_object(content)` (마크다운 코드펜스 제거), `_call_llm_with_retry(prompt, model_id, max_retries=1)` (JSON 파싱 + 재시도 1회 + 실패 시 fallback)
  - `_judge_single_issue(issue, developer_level, use_mock, tech_stack)` → `asyncio.gather(..., return_exceptions=True)` 병렬

### 작업 목록
1. **의존성** — `backend/m2/pyproject.toml`에 `langchain-anthropic` 추가 (현재 LLM 의존성 전무).
2. **analyzer 시그니처 확장** — `analyze(pr_diff, agent)` → context를 받도록 (`analyze(pr_diff, agent, context=None)`), `run_single_agent`에서 `payload.context` 전달.
3. **judge 모듈 신규** — `app/services/llm_judge.py` (dev2 미러, 단 app/ contract 타입에 맞춤: `IssueItem`/`IssueSummary`).
4. **프롬프트 빌더** — context 3필드를 프롬프트에 주입:
   - coding_conventions → 컨벤션 위반 가중
   - previous_pr_issues → 반복 실수면 severity 상향/강조
   - architecture_docs → 아키텍처 맥락 근거
5. **orchestrator/contract 연결** — judge 후 issues/summary 재계산 → `build_agent_result`.
6. **graceful** — LLM 미설정(USE_MOCK_LLM)·타임아웃·파싱실패 시 **원본 도구 결과 유지**(judge 없이 통과).
7. **테스트** — USE_MOCK_LLM=true 기준 mock 경로로 (severity 재판단, Minor 스킵, 예외 시 원본 유지).

### 주의
- `MODULE_CONTRACT.md:37` `uses_kms: false` / "context 수신하나 미사용" → 구현 후 갱신 필요.
- 팀 규칙: USE_MOCK_LLM으로 코드 변경 없이 전환, LLM 응답은 파싱/검증 후 사용, SQL은 파라미터 바인딩.

---

## 4. 주요 파일 (빠른 참조)

```
backend/m2/
├── app/
│   ├── orchestrator.py          ← run_m2_orchestration (Part1·2 연결 지점)
│   ├── analyzer.py              ← analyze() 순수 도구 기반, context 미사용 (확장 대상)
│   ├── contract.py              ← M2OrchestrateResponse (kms_used 추가), build_agent_result
│   ├── clients/m4_client.py     ← graceful httpx 패턴 (kms_client 미러 원본)
│   └── services/result_mapper.py← build_m4_request (context 미포함)
├── dev2/nodes/llm_judge.py      ← LLM-judge 청사진 (미러링 원본, 미연결)
└── pyproject.toml               ← LLM 의존성 없음 (langchain-anthropic 추가 대상)

backend/_shared/shared/contracts.py  ← AnalysisContext, M2*, M0Ingest* (KmsSearch* 추가 대상)
backend/_shared/contracts.py         ← 중복본 (동기화 여부 확인)
backend/m0/app/main.py               ← /health,/ingest만 (검색 없음 = 블로커)
```

---

## 5. 다음 세션 시작 명령어 예시

```
# Part 1 (작고 안전 — 먼저 권장)
KMS context 채우기 Part 1 구현: shared/contracts.py에 KmsSearch* 추가하고
app/clients/kms_client.py 만들고 orchestrator에 graceful 연결해줘

# Part 2 (큰 작업)
dev2/nodes/llm_judge.py 청사진 그대로 app/services/llm_judge.py 만들어서
analyzer가 context 활용하도록 연결해줘 (USE_MOCK_LLM mock 경로 포함)
```
