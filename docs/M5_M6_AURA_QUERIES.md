# M5·M6 Aura 조회 가이드

Neo4j Aura의 Query에서 아래 파일의 쿼리를 하나씩 실행한다. 구조 확인은 Graph 보기, 집계·URL·시간 확인은 Table 보기를 사용한다. 모든 쿼리는 조회 전용이며 YouTube API를 호출하지 않는다.

[전체 Cypher 쿼리](M5_M6_AURA_QUERIES.cypher)

| 쿼리 이름 | 확인 내용 |
| --- | --- |
| ontology_layers | 4-layer 주요 노드 수 |
| ontology_graph | 도메인·개념·메커니즘·코드 및 원인·컴포넌트 연결 |
| sql_injection_graph | SQLi 개념 주변 온톨로지 |
| youtube_graph | Concept → 검색 풀 → 영상 연결 |
| youtube_links_and_timestamps | 실제 YouTube URL과 생성·수정·수집·만료 시각 |
| django_parameterized_query | SQLi + parameterized_query + Django 맥락의 저장 영상 |
| pool_refresh_status | 검색 풀별 저장 건수와 재수집 대상 시각 |
| collection_budget | 일자별 예약된 검색 호출 수 |

M5 시간 속성은 Unix epoch seconds이므로 datetime({epochSeconds: ...})으로 변환한다. M6의 created_at/updated_at은 Neo4j datetime 속성이다. 검색 풀의 refresh_eligible_at은 기본 7일 정책에 따른 대상 시각이며, 실제 실행 시각은 수집기 실행 및 예산에 따라 결정된다. candidate_order는 검색 풀 내부 후보 순서이며 추천 API의 의도별 rank와 구분한다.

기준 데이터: 2026-11-12 Aura 적재 결과는 개념 16개, 도메인 2개, 메커니즘 27개, 코드 예제 29개, 검색 풀 11개, 고유 영상 139개다. 갱신·정리 이후 건수는 달라질 수 있다.
