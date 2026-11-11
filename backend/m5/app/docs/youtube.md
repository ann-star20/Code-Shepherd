# YouTube 추천 연동 안내

현재 API 계약은 [M5 README](../../README.md)를 기준으로 합니다. 이전 UI 시나리오는 설계안이며 코드 기반의 현재 동작과 차이가 있어 이 안내로 대체했습니다. 과거 본문은 Git 이력에 남아 있습니다.

- POST /youtube/ranked에 concept_name을 필수로 전달합니다.
- mechanism_name, code_id, code_lang, code_framework는 선택값입니다.
- code_id만으로 서버가 언어·프레임워크를 조회하지 않습니다. code_lang·code_framework를 직접 전달하세요.
- 추천은 규칙 기반 검색어 우선순위입니다. 항상 5개 영상이 반환되는 보장은 없습니다.
- 검색 실패 시 해당 결과는 생략됩니다. rank 공백·같은 영상 중복이 가능합니다.
- 노드 선택·로딩 애니메이션 등 UI 표현은 이 API의 보장 범위에 포함되지 않습니다.

전체 데이터 흐름은 [M5·M6 아키텍처](../../../../docs/M5_M6_ARCHITECTURE.md)를 참고하세요.
