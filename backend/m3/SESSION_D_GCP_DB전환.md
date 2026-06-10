# SESSION D — 리뷰 결과를 GCP PostgreSQL 에 저장 (SQLite → 클라우드) (VS Code 복붙용)

> 목적: 지금 로컬 파일(SQLite `dev3_demo.db`)에만 저장되는 **리뷰 결과(review_results)** 를
> **POSTGRES_URL 이 있으면 GCP PostgreSQL** 에, 없으면 지금처럼 SQLite 에 저장하도록 한다.
> → 서버 재시작에도 안 날아가고, 팀이 같은 결과를 조회. (`persist_pg` 가 쓰는 것과 동일한 fallback 패턴)

> 범위: **m3** — `test-performance-agent/persist.py`(저장/조회) + 이를 호출하는 `app/main.py`(/review·GET /review) + 그 테스트. GCP 쪽은 `review_results` 테이블 추가 마이그레이션 1건.

---

```
너는 우리 팀 시니어 백엔드 엔지니어다. 작업 디렉토리: C:\Users\user\Code-Shepherd\backend\m3
테스트: py -m pytest --tb=short -q  (python.exe 는 Store 스텁 → py 런처 사용, 또는 .venv 활성화)

[작업 방식]
- tdd-workflow 스킬로 테스트부터(TDD는 항상). 외부 DB 없이 검증한다(psycopg2 는 mock).
- 막히면 systematic-debugging / verification-before-completion 스킬 활용 가능.
- 구현 방법(별도 *_pg 함수 추가 vs save_review/get_review 내부 분기)은 코드를 읽고 네가 가장 깔끔한 쪽으로 정해라.

[이미 있는 것 — 재사용, 새로 짜지 말 것]
persist.py 안에:
- save_review(owner,repo,pr_number,verdict,comment,issues) / get_review(...) : 현재 SQLite 전용
- review_results 테이블: SQLite SCHEMA 에는 이미 존재
- persist_pg(...) : scan_issues/scan_summaries 의 PostgreSQL 경로 (psycopg2, Json, ON CONFLICT UPSERT)
- _pg_url() : POSTGRES_URL 을 env 또는 .env 에서 읽음 (있으면 PG, 없으면 None)
- ensure_scan_summaries(conn) : "없으면 만드는" DDL 헬퍼 패턴
→ review_results 의 PG 경로는 위 persist_pg/_pg_url/ensure_* 패턴을 그대로 본떠 만든다.

[목표]
1. POSTGRES_URL 이 있으면 review_results 를 GCP PostgreSQL 에 저장/조회, 없으면 지금처럼 SQLite.
2. review_results 의 PostgreSQL DDL 추가(owner/repo/pr_number PK, verdict/comment TEXT, issues JSONB) + ensure 헬퍼.
3. GCP DB 에 review_results 를 만드는 마이그레이션 SQL 을 별도 산출(실행은 DB 권한자가).

[반드시 지킬 것 — 합격 기준]
- POSTGRES_URL 이 없을 때 기존 SQLite 동작과 기존 테스트는 100% 그대로(회귀 0).
- DB 접속 URL·자격증명은 .env 에만. 코드/문서/깃에 실제 값 절대 안 적음.
- 가짜 저장/가짜 성공 금지 — PG 연결 실패 시 정직하게 에러 로그(이미 저장된 SQLite 결과를 덮어쓰지 말 것).

[TDD]
- SQLite fallback: POSTGRES_URL 없을 때 save_review/get_review 가 지금과 동일하게 동작(기존 테스트 green 유지).
- PG 경로: psycopg2 를 mock/monkeypatch 해서 INSERT(UPSERT)·SELECT 가 올바른 SQL/인자로 불리는지 검증(실 DB 불필요). persist_pg 테스트가 있으면 그 패턴 재사용.
- 경계 케이스(같은 PR 재저장 → UPSERT 갱신, 결과 없음 → None/빈결과)는 네가 더 생각해서 테스트.

[끝나면]
- [변경 파일 / 테스트 결과 / review_results PG 마이그레이션 SQL(따로)] 정리.
- POSTGRES_URL 을 m3 .env 에 넣고 재시작하면 PG 로 전환된다는 점만 메모(값은 적지 말 것).
- 막히면 멈추고 물어봐라.
```

---

## 참고 (사용자용 메모)
- 바뀌는 건 **"저장 장소"** 뿐 — 코드가 알아서 *주소(POSTGRES_URL)가 있으면 클라우드, 없으면 내 컴퓨터*. 분석·코멘트·화면은 그대로.
- 절반은 이미 돼 있어요(`persist_pg` 가 다른 데이터엔 이미 클라우드 저장 중). 이번엔 **리뷰 결과(review_results)** 만 같은 방식으로 확장.
- m3 혼자 가능. 단 **클라우드 DB 접속 주소**는 KMS 팀원과 공유(같은 GCP DB 쓰니까) — 그 주소만 받아서 `.env` 에 넣으면 끝.
- 실제 GCP 에 테이블 만드는 건 DB 권한 있는 사람이 마이그레이션 SQL 한 번 실행.
