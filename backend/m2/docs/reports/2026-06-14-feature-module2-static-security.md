# 중간 보고서 — 2026-06-14 feature/module2-static-security

## 변경 요약
- `backend/m2/.gitignore` — 일회성 로컬 테스트 스크립트(asyncpg_test.py, db_test.py, result.txt, result_all.txt) gitignore 추가

> 이번 세션의 실질적 코드 변경(result_persist.py COALESCE/pr_number 수정, orchestrator.py pr_id 전달, main.py scan-results 엔드포인트, SecurityPage 실데이터 연결, vite.config /m2-api 프록시)은 이전 커밋(a47fd3e9)에 포함됨.

## 중간 평가
| 항목 | 상태 | 비고 |
|------|------|------|
| 기능 구현 완성도 | 완료 | E2E 파이프라인(분석→DB→m4) 정상 |
| 테스트 작성 여부 | 완료 | tests/ 59 passed |
| 문서 업데이트 여부 | 완료 | MODULE_CONTRACT.md, reports/ 갱신 |
| 보안 이슈 없음 | 완료 | SQL 파라미터 바인딩만 사용 |

## 잘 된 점
- review_issue 테이블에 pull_request_id, code_snippet, code_context, name_of_function 정상 저장 (PR 101~106 각 5~16개 이슈)
- COALESCE로 pr_number 기준 pull_request_id 조회, fallback 최신 PR 로직 안정적 동작
- SecurityPage가 목데이터 없이 m2 /scan-results/{pr_id} 실데이터로 연결
- LLM-judge(mock), KMS context 채우기 파이프라인 완성

## 개선 필요 사항
- framework/framework_version: 현재 vulnerable.py 단일 파일 diff라 None — 실 PR diff에 requirements.txt 포함 시 자동 해결
- m0 KMS AmbiguousParameterError($2 IS NULL): m0 담당자에게 CAST(:category AS text) IS NULL 수정 요청 필요
- webhook 502: m3 /verify/tests 오류 — m3 담당자 문제

## 다음 작업
- Week 5 통합 시 m4와 review_issue 칼럼 합의 (severity 매핑 확정)
- USE_MOCK_LLM=false + ANTHROPIC_API_KEY 설정으로 실제 LLM-judge 검증
- m0 KMS 연동 재확인 (CAST 버그 수정 후)
