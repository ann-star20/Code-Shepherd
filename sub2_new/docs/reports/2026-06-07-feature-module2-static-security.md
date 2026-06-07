# 중간 보고서 — 2026-06-07 feature/module2-static-security

## 변경 요약

| 파일 | 변경 목적 |
|------|-----------|
| `pj3_data/DB_SCHEMA.md` | `scan_issues` DDL에 `mistake_type_concept_id TEXT` 추가 (db.py INSERT가 참조, 신규 테이블 생성 시 실패 방지) |
| `sub2_new/dev2/nodes/llm_judge.py` | LLM 응답 코드펜스(```json … ```) 파싱 버그 수정 — `_extract_json_object()` 추가 |
| `sub2_new/common/harness.py` | 팀 공용 표준 정합: `db_pool`(asyncpg) → `db_session_factory`(SQLAlchemy) |
| `sub2_new/common/trace.py` | 팀 공용 trace 유틸 추가 (Week5 통합 시 `common.* → shared.*` 드롭인) |
| `sub2_new/CLAUDE.md` | §6 `run_parallel_agents` 예시를 `db_session_factory`로 갱신 |
| `sub2_new/docs/learning/ai/*.pdf` | 학습노트 3종 (DB 릴레이 / harness / Repository 패턴) |
| `dev2/.env` (gitignore) | LangSmith 환경변수 정합(`LANGCHAIN_*` 병기, `dev2-wooya`) + `DATABASE_URL`/`USE_MOCK_LLM=false` 복구 |

## 중간 평가

| 항목 | 상태 | 비고 |
|------|------|------|
| 기능 구현 완성도 | 🟢 완료 | P3(DDL+E2E 적재) 검증, llm_judge 버그 수정, harness 정합 |
| 테스트 작성 여부 | 🟡 부분 | 기존 테스트(test_nodes 22, dev2 184) 통과. 코드펜스 헬퍼 전용 단위테스트는 미추가(인라인 검증만) |
| 문서 업데이트 여부 | 🟢 완료 | CLAUDE.md §6, DB_SCHEMA.md, 학습노트 |
| 보안 이슈 없음 | 🟢 | 시크릿 커밋 없음(.env gitignore), SQL 파라미터 바인딩 유지 |

## 잘 된 점

- **P3 E2E 라이브 검증**: sqli 케이스를 Cloud SQL에 실제 적재, `mistake_type_concept_id`/`code_snippet`/`name_of_function`/`keyword` 채워짐 확인.
- **llm_judge 버그**: 코드펜스 때문에 SQL 인젝션이 Critical→Major로 격하되던 문제 해결. 수정 후 `severity='Critical'` 적재 + `early_escalation` 라우팅 정상화.
- **Week5 대비 계약 정합**: harness 시그니처를 팀 표준(`db_session_factory`)에 맞춰 통합 리스크 선제 제거.

## 개선 필요 사항

- **semgrep `[WinError 2]`**: subprocess가 semgrep CLI를 PATH에서 못 찾음. 비치명적이나 보안 룰셋 일부 누락. (다음 작업)
- **코드펜스 헬퍼 단위테스트**: `_extract_json_object`에 대한 정식 pytest 케이스 추가 권장.
- **P2-A LangSmith**: 환경변수는 정합 완료. 실제 대시보드 trace 확인은 미수행.

## 다음 작업

- semgrep PATH 문제 해결 (run_tools_node).
- `_extract_json_object` pytest 추가.
- (Week5) `common.* → shared.*` 통합 전환 + 오케스트레이터 연동.
