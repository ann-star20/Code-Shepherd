# 중간 보고서 — 2026-06-15 feature/module2-static-security

## 변경 요약

M2 보안 파이프라인 시각화를 **가짜 고정 타이머 → 실제 분석 실시간 폴링**으로 전환.

| 파일 | 변경 목적 |
|------|----------|
| `backend/m2/app/progress.py` (신규) | task_id 키 인메모리 진행상태 저장(start/set_stage/finish/fail/get, 상한 200). 휘발성 — DB 불필요. |
| `backend/m2/app/main.py` | `POST /orchestrate/run-case/{case_name}`(화이트리스트 검증, vulnerable.py→상대경로 unified diff, 백그라운드 분석, task_id 즉시 반환) + `GET /orchestrate/status/{task_id}`. `_display_file`로 절대경로 축약. |
| `backend/m2/app/orchestrator.py` | `run_single_agent`을 `_analyze_tools`/`_judge`/`_persist_scan` 프리미티브로 분해(동작 동일). `run_m2_orchestration(req, task_id=None)`를 4단계(run_tools→vector_search→llm_judge→store) 실측 타이밍 보고로 재배치. **run_tools 두 에이전트 asyncio.gather 병렬화**(순차 44s→max 34s, 결과 동일). |
| `frontend/src/pages/security/SecurityPage.tsx` | `STAGE_MS` 가짜 타이머 제거. PR 선택 시 run-case 트리거→1초 폴링으로 단계 실시간 반영→done이면 `scan-results/task/{task_id}` 결과 조회. |
| `backend/m2/Dockerfile` | `uv sync` 에 `--extra llm` 추가 — 재빌드 시 LLM 패키지 재현성 확보(실제 LLM-judge용). |
| `backend/m2/tests/test_progress.py` (신규) | progress 모듈 + run-case/status 엔드포인트 단위테스트 8건. |

## 중간 평가

| 항목 | 상태 | 비고 |
|------|------|------|
| 기능 구현 완성도 | 🟢 완료 | run-case→status 폴링 E2E 검증, 실제 LLM-judge 동작 확인 |
| 테스트 작성 여부 | 🟢 완료 | 신규 8건 전부 통과 (전체 77 passed) |
| 문서 업데이트 여부 | 🟡 부분 | 본 보고서. MODULE_CONTRACT는 엔드포인트 추가분 반영 권장 |
| 보안 이슈 없음 | 🟢 | case_name 화이트리스트로 traversal 차단, 상대경로로 원본 미변경 |

## 잘 된 점

- 가짜 애니메이션 제거 — 각 단계가 백엔드 실측 타이밍대로 흐름(run_tools≈34s, vector_search≈7s, llm_judge≈35~48s 실제 Claude, store≈2s).
- `uvicorn --reload`가 분석 중 원본 파일 변경으로 죽던 버그를 상대경로 diff로 해결.
- 도구 병렬화로 run_tools 무손실 ~10s 단축.
- 기존 `run_single_agent`/`/analyze/*` 하위호환 유지.

## 개선 필요 사항

- semgrep(OSS 1.165)이 OWASP 룰셋으로 파일 1개에도 ~34s 고정 비용 — 로컬 번들로는 단축 불가 확인(오히려 느림). 커버리지 유지를 위해 현행 유지.
- 기존 실패 테스트 3건(test_analyzer 2 = 컨테이너 도구 풀패스 resolve, test_persist 1 = sub_category 매핑 스테일) — 이번 변경 무관, 별도 정리 필요.

## 다음 작업

- 실제 LLM-judge 운영 시 비용/지연 모니터링.
- dev 브랜치는 module2-clean과 중복 상태 — PR 전략 검토 필요(아래).
