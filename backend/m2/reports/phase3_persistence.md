# Phase 3 중간보고서 — review_issue 영속화

**일자**: 2026-06-12 | **브랜치**: `feature/module2-static-security`
**상태**: ✅ 완료 (기본 비활성 opt-in, 목 테스트 통과 — 실제 DB 미접속)

## 목표
m2 분석 결과(IssueItem)를 m4 소유 `review_issue` 테이블에 저장.
m4가 INSERT 패턴(파라미터 바인딩, FK는 github_id 서브쿼리로 해결)을 직접 제공함.

## 신규 파일
| 파일 | 역할 |
|------|------|
| `app/services/result_persist.py` | m4 제공 INSERT 실행. async SQLAlchemy. severity/keyword 매핑 |
| `tests/test_persist.py` | 매핑·삽입·graceful — **목 세션 주입(실 DB 미접속)** |

## 수정 파일
- `app/orchestrator.py` — 분석 후 `persist_issues()` 호출(graceful, 비중단).
- `app/contract.py` — `M2OrchestrateResponse.persisted: int` 추가.

## 안전장치 (공유 클라우드 DB 보호)
- **기본 비활성(opt-in)**: `M2_PERSIST_ENABLED`=truthy **그리고** `DATABASE_URL` 있을 때만 실제 INSERT.
- CI/테스트는 기본 OFF → 공유 DB를 건드리지 않음. 테스트는 목 세션 팩토리를 주입해 검증.
- DB 오류는 삼키고 `0` 반환 → 분석 비중단.

## 컬럼 매핑 (IssueItem → review_issue)
| review_issue | 출처 |
|--------------|------|
| `id` | `uuid4()` |
| `pull_request_id` `user_id` | 서브쿼리(github_id) — m2가 값 안 만듦 |
| `github_id` | `developer.id` |
| `agent` | `static_analysis` / `security_scan` |
| `severity` | 매핑(아래) |
| `keyword` (NOT NULL) | rule_id 접두사 기반(아래) |
| `sub_category` | `rule_id` |
| `suggestion` | `IssueItem.suggestion` |
| `programming_language` | 파일 확장자 추론(.py→python 등) |
| `code_context` `code_snippet` `framework` `framework_version` `name_of_function` | m2 미보유 → `null` |

## ⚠️ m4 합의 필요 (잠정값 — 각각 한 곳에서 수정 가능)
1. **severity 매핑** (`_SEVERITY_MAP`): `Critical→critical / Major→high / Minor→medium` (low 미사용).
2. **keyword 규칙** (`_KEYWORD_BY_PREFIX`): `SEC-/OWASP-→security`, `SA-/JS-→static`, fallback=agent 도메인.
3. **DB**: `DATABASE_URL`(asyncpg) async SQLAlchemy 사용.

> review_issue·pull_requests·users는 m4 소유 → severity/keyword는 m4 통계 키와 합의 후 고정(통계 깨짐 방지).

## 켜는 법
m2 환경에 `M2_PERSIST_ENABLED=true` + `DATABASE_URL` 설정.
