# Phase 1 중간보고서 — m2 오케스트레이터 → m4

**일자**: 2026-06-12 | **브랜치**: `feature/module2-static-security`
**상태**: ✅ 완료 (pytest 전체 통과)

## 목표
`pr_diff` 입력 → m2 자체 2개 분석(정적/보안) → m4 `/evaluate` 판정까지 end-to-end로 도는 뼈대.
m3 자리(test_verification/performance)는 `None`으로 비워둔다.

## 신규 파일
| 파일 | 역할 |
|------|------|
| `app/decision.py` | diff를 보고 정적/보안/skip 라우팅 판단 (`decide()` → `AnalysisDecision`) |
| `app/orchestrator.py` | `run_m2_orchestration()` + `run_single_agent()` — 분석 조율 |
| `app/clients/m4_client.py` | m4 `/evaluate` 호출, 미설정·실패 시 graceful `None` |
| `app/services/result_mapper.py` | `AgentResult` → `M4EvaluateRequest`(named 필드) 변환 |
| `app/clients/__init__.py`, `app/services/__init__.py` | 패키지 초기화 |
| `tests/test_decision.py`, `tests/test_orchestrator.py` | 단위·엔드포인트 테스트 |

## 수정 파일
- `app/main.py` — `POST /orchestrate/review` 추가. 기존 `_run_agent`를 `orchestrator.run_single_agent`로 위임(중복 제거). 기존 `/analyze/static`·`/analyze/security`·`/health` **불변**.
- `app/contract.py` — `M2OrchestrateRequest` / `M2OrchestrateResponse` 추가.
- `pyproject.toml` — `httpx`를 런타임 의존성으로 승격(오케스트레이터가 m4 호출에 사용).

## 실행 흐름
```
M2OrchestrateRequest
  → decision.decide()        분석 필요 판단 (skip 가능)
  → skip → status="skip" 반환
  → run_single_agent × 2     static / security (AgentResult)
  → result_mapper            → M4EvaluateRequest (test/perf = None)
  → m4_client.evaluate()     /evaluate (실패·미설정이어도 분석결과는 응답에 포함)
  → M2OrchestrateResponse
```

## 검증된 동작
- Python diff → static+security 둘 다 실행 → m4 verdict 포함 응답
- docs/`.md`만 변경 → `status="skip"`
- `M4_URL` 미설정 → `m4_called=false`, 분석결과는 그대로 반환(graceful fallback)

## plan 대비 의도적 보류 (over-engineering 회피)
- `m0_client.py` / `kms_client.py` / `context_builder.py`는 **생성하지 않음**.
  현재 `analyzer`가 `context`를 소비하지 않아 지금 추가하면 호출되지 않는 dead code가 된다.
  `M2OrchestrateRequest.context`는 받아 그대로 통과만 시키고, 실제 RAG/컨텍스트 연결 시점에 추가한다.

## 불변식 확인
- 기존 엔드포인트·`AgentResult` 계약·기존 테스트 보존
- `shared/contracts.py`, `docs/`, m1/m3/m4 코드 무수정
