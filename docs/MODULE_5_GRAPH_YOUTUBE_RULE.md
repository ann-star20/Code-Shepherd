# M5·M6 역할 분리와 현행 문서

이 경로의 과거 v1.0 설계는 M5에 문서 업로드·LLM 추출·그래프 저장을 함께 배정했습니다. 현재 구현에서는 해당 책임이 M6로 분리되었으므로 과거 설계를 실행 계약으로 사용하지 않습니다. 이전 본문은 Git 이력에서 확인할 수 있습니다.

- M5: Neo4j 개념·메커니즘 조회와 규칙 기반 YouTube 검색 추천
- M6: URL 수집·청킹·개념 추출·중복/유사성 해소·HITL·Neo4j 저장
- 공유 지점: Compose의 neo4j_m6
- M5 POST /extract: 호환용 스텁; 실제 추출·저장을 수행하지 않음
- 현행 추천 경로: POST /youtube/ranked; /youtube/recommend는 없음

API와 실행 방법은 [M5 README](../backend/m5/README.md), [M6 README](../backend/m6/README.md)를 참고하세요. 데이터 모델·해소 정책·제약의 기준 문서는 [통합 아키텍처](M5_M6_ARCHITECTURE.md)입니다. 과거의 Module5Document·source_system 고정값·파일 업로드·Aura 필수 사용 규칙은 현재 M5 구현 계약이 아닙니다.
