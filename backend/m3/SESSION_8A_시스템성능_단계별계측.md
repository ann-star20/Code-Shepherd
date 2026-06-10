# SESSION 8A — 시스템 성능: 단계별(워터폴) 계측 (VS Code 복붙용)

> 목적: "어디서 몇 초"를 **단계별로 쪼개** 측정한다 — clone→coverage→탐지기4→enrich→RAG→집계→LLM→게시→저장. 여러 PR로 돌려 **p50/p95**와 **병목**을 낸다.
> 범위: m3 분석/리뷰 경로. **이미 `@instrument` 데코레이터가 각 노드에 있다** → 새로 계측 박지 말고 그 span 시간을 **수확·집계**하는 게 핵심.
> 선행: **8-0b(6탐지기 연결)·8-0c(RAG ON) 완료 후**. 탐지기가 6개(edge_cases·memory_leak 추가)·RAG 기본 ON 상태에서 측정해야 진짜 통계다. docker compose의 m3 컨테이너에서 실행.

## 배경 (왜 이게 필요)
- 지금은 엔드포인트 통시간(verify 7.3s·perf 5.3s·review 1.5s)만 있어 **내부가 블랙박스**다. clone이 느린지 coverage(pytest)가 느린지 모른다.
- `test-performance-agent/harness.py`의 `@instrument`가 노드별 시간을 이미 찍는다(tracing). LangSmith 켜져 있으면 거기도 남는다. → **그 값을 모아 표로** 만들면 끝.

---

```
너는 우리 팀 백엔드/플랫폼 엔지니어다. 작업 디렉토리: C:\Users\user\Code-Shepherd\backend\m3
실행 환경: docker compose 의 m3 컨테이너(uv). 테스트는 컨테이너 안에서 pytest.

[작업 방식]
- TDD로(테스트 먼저). superpowers:test-driven-development 스킬 사용. (설치된 스킬: tdd-workflow, systematic-debugging 등 — 막히면 활용)
- 기존 harness.py 의 @instrument 계측을 재사용한다. 중복 계측 코드를 새로 박지 말 것.

[선행 점검 — 평가 전 "구현이 멀쩡한가" 먼저 ★]
성능평가는 대상 코드가 정상일 때만 의미 있다. 계측 착수 전:
- m3 분석 영역 기존 테스트 green 확인(uv run --extra test pytest; test_task9_main·복잡도·커버리지 등).
- 데모 입력(fixtures/sample_repo 또는 -dev3-demo #4)으로 run()/verify·perf 엔드포인트 스모크 1회 —
  이슈가 정상 산출되고 각 노드 @instrument span(노드명·ms)이 실제로 찍히는지 눈으로 확인.
- span 이 안 찍히거나 빈/이상 결과면 그게 8A의 선결 버그 → 멈추고 보고(또는 작은 것만 고치고 기록).
  깨진 파이프라인 위에서 시간 숫자를 내지 말 것.

[배경/문제]
m3 분석은 clone→coverage(pytest 샌드박스)→탐지기4(coverage/missing_funcs/nplus1/complexity)→enrich→(RAG)→집계→LLM refine→GitHub 게시→persist 순으로 흐른다.
지금은 단계별 시간이 안 보인다. "어디서 몇 초 걸리고 어디가 병목인지"를 정량으로 내야 한다.

[목표]
1. 단계별 시간 수확기: harness.py 의 instrument span(노드명·소요ms)을 한 번의 분석 실행에서 모아
   {stage: ms} 딕셔너리로 반환하는 작은 수집기(예: bench/latency.py)를 만든다.
   - 단계 최소 집합: parse_diff, clone(prepare_repo), coverage(sandbox/pytest), missing_funcs,
     edge_cases(TEST-003), nplus1, complexity, memory_leak(PERF-003),
     enrich(code_context+framework), rag(기본 ON), aggregate, refine(LLM),
     github_post, persist, end_to_end.  ※ 8-0에서 6탐지기 연결됨 → 6개 모두 단계로.
2. 여러 PR로 반복: 크기가 다른 PR 최소 5개(작은/중간/큰 diff, 의존성 有/無 섞어)로 N회 실행.
   - 데모 레포(kskt1234-netizen/-dev3-demo PR #1~#4) + fixtures/sample_repo 활용 가능.
3. 집계 리포트: 단계별 p50·p95(+min/max), end-to-end, **병목 1~2개 명시**. 표(markdown)로 출력.
4. cold vs warm 구분: 첫 실행(모델 로드·첫 clone)과 이후를 나눠 표기(가짜로 합치지 말 것).

[반드시 지킬 것 — 합격 기준]
- 측정 못 한 단계는 빈칸/생략(가짜 숫자 금지). RAG 꺼져 있으면 rag 행은 "(off)".
- 표본 수(N), PR 목록, 환경(컨테이너 내 직접실행 vs docker 샌드박스)을 리포트에 명시.
- 1커맨드 재실행 가능(예: uv run python bench/latency.py). 결과는 bench/리포트.md 로 저장.

[TDD]
- 수집기 단위테스트: 가짜 instrument span 목록 → 기대 {stage:ms} 집계·p50/p95 계산 검증.
- 빈/일부 누락 span → 해당 단계 생략(가짜 0 금지) 검증.

[끝나면]
- [단계별 p50/p95 표 / N·PR목록 / 병목 / cold·warm / 한계] 정리.
- 발표자료 §3-1(시스템 성능)에 이 표를 꽂을 수 있게 markdown 그대로 남겨라.
- 막히면 멈추고 물어봐라.
```

---

## 참고 (사용자용 메모)
- 이건 "AI 잘 맞히나"가 아니라 **"빠른가/어디가 느린가"** 평가예요. 발표에선 "단계별로 재보니 **clone+커버리지 측정이 대부분**이고, 탐지기 자체는 ms 단위"처럼 말하면 강합니다.
- 새 라이브러리 필요 없음. 이미 박힌 계측을 모으는 거라 8개 중 제일 가벼움 → **여기부터 시작** 추천.
