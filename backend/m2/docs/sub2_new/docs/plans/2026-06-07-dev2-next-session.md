# 내일 할 일 — Dev2 (2026-06-07)

> 브랜치: `feature/module2-static-security` | 작성일: 2026-06-06
> 우선순위는 product-lens(ICE) 분석 기준 → **P3 먼저, 키 되면 P2-A, P2 후속은 미루기**

---

## 0. 어제(6/6)까지 완료

- ✅ bge-m3 RAG 임베딩 전환 + E2E 검증 (N+1 유사도 0.751)
- ✅ M2 피드백 필드(code_snippet 경로버그 수정, name_of_function AST 추출) + DB 릴레이
- ✅ task-interpretation-agent에서 데이터셋/모듈 복구 + 푸시 (test-performance/pr-comment는 제외, M3 컬럼 정의 파일은 살림)
- ✅ **P2-C Repository 패턴 리팩터링** (`dev2/repositories/`, nodes 전환, db.py print 제거) — 커밋 `d0b5e9d`
- 테스트: dev2 184 passed (실패 14건은 Airflow 미설치, 무관)

---

## 1. 우선순위 (product-lens 결론)

| 순위 | 작업 | ICE | 이유 |
|------|------|-----|------|
| 1 | **P3 Cloud SQL DDL + M2 E2E** | 6.7 | 제품 핵심(결과 적재 증명) + 실제 DDL 버그 제거. 블로커 없음 |
| 2 | **P2-A LangSmith 런타임** | 15* | ROI 최고지만 `LANGCHAIN_API_KEY` 발급이 선행 조건(*키 있을 때) |
| 3 | **P2 후속 API Repository화** | 2.0 | 내부 정리, 신입 사용자 가치 0 → Week 5 통합 직전으로 미룸 |

---

## 2. P3 — Cloud SQL DDL 적재 + M2 E2E  ⭐ 먼저

**무엇을**: `pj3_data/DB_SCHEMA.md` DDL로 테이블 생성 → M2 케이스 1개 돌려 `scan_issues`에 적재되는지 확인.

**왜**: Dev2의 존재 이유 = "스캔 결과가 실제로 DB에 저장돼 M4가 쓸 수 있나?"를 라이브 인프라에서 증명. M2→DB→M4 경로의 최종 검증.

**선행 — DDL 버그부터 보강 (⚠️ +10분)**
- `DB_SCHEMA.md` DDL에 `mistake_type_concept_id` 컬럼 누락. `db.py` INSERT(`insert_scan_issues`)는 이 컬럼을 참조함 → 신규 테이블 생성 시 INSERT 실패.
- 보강: `scan_issues` DDL에 `mistake_type_concept_id TEXT` 추가 (additive, 비파괴).
- 참고: 라이브 인스턴스엔 이미 존재해 현재는 동작 중(어제 name_of_function도 ALTER로 추가됨).

**순서**
1. `DB_SCHEMA.md` DDL에 `mistake_type_concept_id` 추가.
2. (신규 테이블 시) DDL 실행. 기존 라이브면 컬럼 존재 여부만 점검.
3. M2 케이스 1개(예: sqli_case) `run_case.py` 또는 `run_dev2()` 실행 → `scan_issues` 행 + `code_snippet`/`name_of_function`/`keyword` 채워졌는지 확인.
4. `.env`는 이미 Cloud SQL(34.22.101.111 / tasklink) 설정됨, asyncpg 0.31.0 설치됨.

**예상**: 30~60분 (DDL 보강 포함)

**시작 명령**
```
pj3_data/DB_SCHEMA.md의 scan_issues DDL에 mistake_type_concept_id 추가하고,
M2 sqli 케이스 하나 돌려서 Cloud SQL scan_issues에 적재되는지 E2E 확인해줘
```

---

## 3. P2-A — LangSmith 런타임 확인  (키 있을 때만)

**무엇을**: 실제 `LANGCHAIN_API_KEY`로 파이프라인 1회 실행 → LangSmith 대시보드에 trace 뜨는지 확인.

**왜**: 멀티에이전트 디버깅/데모에 관측성은 필수(CLAUDE.md §3). 코드(`common/harness.py` `instrument()`)는 이미 준비됨.

**블로커**: 개인 `LANGCHAIN_API_KEY` 발급. **키 없으면 진행 불가 → park.**

**순서 (키 확보 후)**
1. `.env`에 `LANGCHAIN_TRACING_V2=true`, `LANGCHAIN_API_KEY=ls__...`, `LANGCHAIN_PROJECT=dev2-<github_id>` 설정.
2. `dev2` 파이프라인 1회 실행.
3. LangSmith 대시보드에서 trace(서브 trace 포함) 확인.

**예상**: 15~30분 (키 있으면)

---

## 4. P2 후속 — API 레이어 Repository화  (미룸)

**무엇을**: `api/scan.py`, `api/issues.py`, `api/insights.py`도 raw SQL 대신 Repository 경유로 전환.

**왜 지금 안 하나**: 내부 일관성 작업이라 신입 사용자 가치가 지금은 0(product-lens ICE 2.0). Week 5 통합 직전 또는 그 코드를 어차피 손볼 때 묶어서.

**미리 알아둘 점 (할 때)**
- `scan.py`는 nodes와 비슷해 쉬움.
- `issues.py`/`insights.py`는 엔드포인트 안에서 `AsyncSessionLocal`로 **직접 SELECT** 중 → **읽기용 Repository 메서드**를 새로 설계해야 함.
- `test_insights`가 `dev2.db.AsyncSessionLocal`을 패치하므로 테스트도 seam에 맞게 수정.

**예상**: 1.5~2.5시간

---

## 5. 빠른 참조

```
sub2_new/
├── dev2/repositories/scan_repository.py   ← 어제 만든 Repository (인터페이스+구현체+팩토리)
├── dev2/db.py                             ← raw SQL (구현체가 위임). INSERT가 mistake_type_concept_id 참조
├── dev2/nodes/{store,aggregate}.py        ← Repository 사용 중
├── dev2/api/{scan,issues,insights}.py     ← P2 후속 대상 (아직 raw SQL)
├── common/harness.py                      ← instrument() = LangSmith 데코레이터 (P2-A)
└── pj3_data/DB_SCHEMA.md                  ← P3 대상, mistake_type_concept_id 누락 (보강 필요)
```

**환경**: USE_MOCK_LLM=false, PGVECTOR_DIMENSION=1024, EMBEDDING_MODEL=BAAI/bge-m3, Cloud SQL 설정됨.
**미해결(별건)**: chunk_embeddings에 N+1 가이드 청크 중복 적재(유사 검색 시 동일 결과 3건) — 데이터 시딩 점검 필요.

---

## 6. 시작 프롬프트 예시

```
# P3 (추천)
pj3_data/DB_SCHEMA.md에 mistake_type_concept_id 추가하고 M2 케이스 Cloud SQL E2E 적재 확인해줘

# P2-A (키 발급했으면)
.env에 LangSmith 키 넣고 dev2 파이프라인 실행해서 대시보드에 trace 뜨는지 확인해줘

# P2 후속 (통합 직전)
api/scan·issues·insights도 Repository 경유로 전환해줘 (읽기용 메서드 설계 포함)
```
