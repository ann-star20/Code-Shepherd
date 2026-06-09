# [마스터 지침] 3-Factor 하이브리드 수렴 서비스 레이어 및 영속성 커널 완성 세션

외부 비정형 기술 문서(HTML/Markdown/URL)를 지각하고 추론하여 정형 RDB 및 의미론적 지식 그래프(Neo4j)에 멱등적으로 적재하는 **"지능형 지식 수렴 에이전트 플랫폼"**을 구축 중입니다. 구형 SAME_AS 분기를 제거하고 `USE_REAL_LLM` / `USE_REAL_EMBEDDING` 환경 플래그 가드레일이 탑재된 최신 `app/worker/tasks.py` 워커가 안착되었습니다. 이를 연동 드라이브할 `GraphWriterService` 실물 구현체를 완성해 주세요.

수집 파이프라인 워커와 3-Factor 수렴 수식의 물리 작동 검증을 완료했습니다. 이제 에이전트 추론 점수의 투명성과 프론트엔드 HITL 대시보드 렌더링 연동을 위해, 하이브리드 리졸버 점수를 RDB 스테이징 테이블에 영속화하는 최종 작업을 완수해 주세요.

## 0. 요구 명세
1. **`staging_concepts` 테이블 컬럼 확장**:
   * `infer_action` (TEXT), `infer_score` (FLOAT), `target_concept_name` (TEXT) 컬럼을 보완하여 추출 시점의 하이브리드 계산 가수를 영구 보관할 수 있게 하세요.
2. **`app/worker/tasks.py` - Extractor 후행 바인딩**:
   * `_do_extract` 시점에 `hybrid_resolve` 선행 연산을 수행하여 계산된 점수와 추천 액션 플래그를 `staging_concepts`에 함께 UPSERT 적재하도록 흐름을 고도화하세요.
3. **`GraphWriterService` 최적화**:
   * 3단계 적재 기동 시, 처음부터 점수를 재계산하지 않고 스테이징에 이미 완벽하게 가이드라인이 잡힌 `infer_action`과 점수를 읽어와 Neo4j 4-레이어 자석 적재 및 `[:RELATED_TO]` 가교선 조인을 처리하도록 컴팩트하게 다듬어 주세요.


