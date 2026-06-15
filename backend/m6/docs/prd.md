# prd.md — 자동 지식그래프 구축 파이프라인 PRD

> 본 지침서는 **현재 구현 코드**(`neo4j_repo.py`, `hybrid_resolver.py`, `seed_postgres.py`, `schema.sql`, `worker/tasks.py`)에서 역추출한 유효 기획 의도 단권화본이다. 타 프로젝트 사이드바+신규 페이지 이식 시 뼈대로 사용한다.

## 1.1 개요 및 목적

외부 기술 공식 문서·사내 KB를 크롤링하여, AI 에이전트가 **4-Layer 지식 온톨로지**(Domain→Concept→Mechanism/Property/RootCause/Component→CodeExample)를 자동 추출하고, **PostgreSQL+pgvector**(시맨틱 검색)와 **Neo4j**(고차원 관계 추론) 하이브리드 스토리지에 인간 개입을 최소화하면서 **멱등(idempotent)하게** 적재하는 파이프라인.

목적: 보안(OWASP Top 10)·성능(CWE 안티패턴) 지식을 정형 그래프로 축적하고, 중복·불일치·누락 없이 점진적 증분 갱신을 보장한다.

## 1.2 핵심 기능 범위 (Scope)

| 영역 | 범위 |
|------|------|
| 입력 | URL 등록 + Pre-scan(프레임워크/언어/버전 추론, `framework_metadata` DB 주도) |
| 수집 | Crawler(DOM 정제·텍스트 추출), ETag/`content_hash` 기반 중복 차단 |
| 추출 | Gemini(`gemini-2.5-flash`) JSON 추출 → `staging_concepts` DRAFT 적재 |
| 검증 | HITL 승인 게이트(`/approve` `/reject` `/commit` `/diff`) |
| 적재 | Graph Writer(domains→다중라벨 MERGE) + Link Resolver(3-Factor 유사도) |
| 가시화 | 3-Layer 토폴로지 뷰, 가상 노드 미리보기, 컨셉 인스펙터 |

비범위: 자연어 질의응답·RAG 검색 UI, 멀티테넌시.

## 1.3 사용자 및 시스템 흐름 (Workflow)

```
관리자 → URL 입력 → Pre-scan(신뢰도<0.8 시 HITL 메타 보정)
   → Crawl → Extract(DRAFT+사전 유사도 산출)
   → HITL 검토(가상 노드 미리보기/승인·거부)
   → Write & Resolve(MERGE/RELATED_TO/NEW) → COMMITTED
```
- 실시간 진행은 **단일 채널 SSE**(`/api/pipeline/stream/{session_id}`)로 5단계 인디케이터에 반영.
- 상태 머신: 문서 `PENDING→CRAWLING→EXTRACTING→EXTRACTED→COMMITTED|FAILED`.

## ★ 버그 방지 및 개선 요건 (PRD)

- ★ **신뢰도 게이트**: Pre-scan `infer_confidence < 0.8` 또는 미탐지 도메인 → HITL 인터락(자동 진행 금지). 누락 시 잘못된 프레임워크로 오추출.
- ★ **FAILED 클린업 멱등성**: 재실행 전 해당 `session_id`의 `staging_concepts`/`pipeline_logs` 정리 후 `PENDING` 리셋(부분 적재 잔존 방지).
- ★ **HITL 동시성**: 승인은 `SELECT FOR UPDATE SKIP LOCKED`로 직렬화(이중 커밋 방지).
- ★ **추적성**: `doc_id`를 Pre-scan→Commit 전 단계 전파해 출처 역추적(`REFERENCES` 엣지) 보장.
