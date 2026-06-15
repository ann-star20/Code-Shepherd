# INTEGRATION READINESS — D5 통합 게이트 집계

> 2026-06-12 (D5). 목표: 팀 스택에 m3로 drop-in 취합 가능한 상태.
> 판정 기준: CLAUDE.md 통합 불변조건 + D5 게이트 4종.

## 집계

| 게이트 | 기준 | 판정 | 증빙 |
|---|---|---|---|
| **G1 계약** | http_adapter ↔ 기존 m3 M3ReviewRequest/Response 필드 단위 일치 | ✅ PASS | 아래 대조표 + 실응답 덤프 (데모 PR #4) |
| **G2 임베딩** | bge-m3 1024d로 make eval 12/12 유지 | ✅ PASS | run_20260612-160913 — 12/12, 환각 0, 첫 시도 통과 |
| **G3 DB** | review_issue 실 스키마 INSERT 성공 | ✅ PASS | GCP Cloud SQL — DB_HOST/PORT/NAME/USER/PASSWORD 연결. 실 INSERT +2행 확인 (2026-06-12, 86→88). |
| **G4 격리** | 팀 파일 미수정 + .env만으로 직접실행↔도커 전환 | ✅ PASS | D5 세션은 Code-Shepherd 읽기 전용 접근만 수행 (기존 dirty 39건은 전부 D5 이전 mtime≤06-11, 금지 4종 코드 무변경 — m0 건은 런타임 data/storage/) · dev3-m3:latest 빌드+기동+/health 200 · compose override 절차 문서화 |

**종합: 4/4 PASS — 모든 게이트 통과.**

## G1 — 계약 필드 대조표

정본: `Code-Shepherd/backend/_shared/shared/contracts.py`

### M3ReviewRequest (m1 → m3)

| 필드 | 팀 정본 | dev3 http_adapter | 판정 |
|---|---|---|---|
| task_id | str | str | ✅ |
| pr_id | str | str | ✅ |
| repository | str ("owner/repo") | str | ✅ |
| pr_number | int | int | ✅ |
| static_analysis | M2AnalyzeResponse \| None | Any=None (수용, 미사용) | ✅ 와이어 호환 |
| security_scan | M2AnalyzeResponse \| None | Any=None | ✅ |
| test_verification | M3VerifyResponse \| None | Any=None | ✅ |
| performance | M3VerifyResponse \| None | Any=None | ✅ |
| developer | DeveloperProfile \| None | Any=None | ✅ |
| trace_id | str \| None | str \| None | ✅ |

### M3ReviewResponse (m3 → m1)

| 필드 | 팀 정본 | dev3 | 판정 |
|---|---|---|---|
| task_id | str | str | ✅ |
| pr_id | str | str | ✅ |
| verdict | Literal["lgtm","rework","escalate"] | 동일 Literal | ✅ |
| comment_posted | bool | bool | ✅ |
| comment_url | str \| None | str \| None | ✅ |
| persisted | bool | bool | ✅ |
| trace | (없음) | list[dict] \| None — **옵셔널 추가** | ✅ m1 pydantic은 unknown 필드 무시 |

### GET /review/{owner}/{repo}/{pr_number} (프론트 → m3)

응답 키 9종 동일: owner, repo, pr_number, found, verdict, verdict_reason, comment, issues[], rich_issues[] (+옵셔널 trace).
- issues[i]: severity, file, line, message, rule_id, suggestion, rag_context, source_url — ReviewPage.tsx 기대 8키 일치
- rich_issues[i]: agent, severity, keyword, sub_category, code_context, code_snippet, suggestion, name_of_function, programming_language, framework — 10키 일치

### 실응답 덤프 (2026-06-12, 데모 PR #4)

```json
{
  "task_id": "d5-g1-dump-0001",
  "pr_id": "4",
  "verdict": "rework",
  "comment_posted": true,
  "comment_url": "https://github.com/kskt1234-netizen/-dev3-demo/pull/4#issuecomment-4688426305",
  "persisted": true
}
```

### dev3 verdict 매핑 규칙

| dev3 파이프라인 결과 | m3 verdict |
|---|---|
| violation findings ≥ 1 | rework |
| gap_report (지침공백) | escalate |
| findings 없음 | lgtm |

## G2 — 임베딩 전환 상세

- 기본: **bge-m3 (ollama, 1024d)** / 폴백: openai text-embedding-3-small (1536d) — `.env` `EMBEDDING_PROVIDER`로만 전환
- 사전 검증: ollama `/api/embed` 1024차원 응답 확인
- 안전장치: 모델별 캐시 키 분리 + Chroma 컬렉션 metadata에 provider/model/dims 기록 → retrieve가 인덱스/질의 모델 불일치 시 즉시 에러 (자동 폴백 없음 — 조용한 인덱스 오염 방지)
- 원복 경로: `.chroma_backup_openai` 백업 보존 + `EMBEDDING_PROVIDER=openai && make reindex`
- judge 프롬프트 무변경 (불변조건 준수)

## G3 — DB 상세 (2026-06-12 PASS)

- 연결: GCP Cloud SQL — `DB_HOST/PORT/NAME/USER/PASSWORD` (sslmode=require)
- 검증: SELECT 1 OK → INSERT +2행 (86→88) 확인
- 테이블: `review_issue` (단수, gen_random_uuid() PK, pull_request_id/user_id 서브쿼리)
- `pull_requests` 서브쿼리: `github_pr_number` + `repository_full_name`으로 pull_request_id/user_id 매칭
- ENABLE_DB_WRITE: 검증 후 false 복귀 확인 (eval 중 INSERT 없음)
- psycopg2-binary==2.9.10 requirements.txt 추가

## G4 — 격리 상세

- 팀 파일 4종(docker-compose.yml, backend/api-core, backend/m0, frontend) 무수정 — 읽기만 수행
- 교체는 `docker-compose.override.yml` **추가**로만 (절차: docs/INTEGRATION_GUIDE.md)
- 직접실행↔도커 전환 .env 차이표: INTEGRATION_GUIDE.md §4
- 이미지: 코드만 포함, .env·키·인덱스 미포함 (.dockerignore)

## 알려진 리스크

| 리스크 | 내용 / 완화 |
|---|---|
| m1 60초 타임아웃 | 캐시 미스 시 ~25-40초 — 통과하나 여유 적음. 리허설 캐시 워밍으로 <5초 |
| ollama 미기동 | 자동 폴백 없음(의도) — 명시 에러 + EMBEDDING_PROVIDER=openai 폴백 절차 안내 |
| 핫스왑 후 컨테이너 | 도커 운용 시 reindex 후 컨테이너 재시작 필요 (Chroma 핸들 캐시) |

## 발표 수치 (게이트 4 박제 — bge-m3 기준 최종 측정)

탐지율 6/6 (100%) · 오탐 0건 · 환각률 0% · 지침공백 2/2 (100%) · **전체 12/12 PASS**
(run_20260612-163506, temperature 0, claude-sonnet-4-6, bge-m3 1024d)
