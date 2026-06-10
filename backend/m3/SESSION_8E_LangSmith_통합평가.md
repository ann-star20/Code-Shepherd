# SESSION 8E — LangSmith 통합 평가 (Dataset·Experiment·Evaluator) (VS Code 복붙용)

> 목적: 8B/8C/8D의 평가셋·채점기를 **LangSmith**로 묶어 — 평가셋=Dataset, 에이전트 실행=Experiment, 채점기=Evaluator로 등록하고, **한 대시보드에서 점수·회귀**를 추적한다.
> 범위: 평가 오케스트레이션/관측 레이어. 탐지기·코멘트·RAG 로직은 안 바꾼다(평가를 LangSmith로 옮길 뿐).
> 선행: **8B(탐지)·8C(코멘트)·8D(RAG) 중 최소 하나의 평가셋·채점기 존재** + `LANGCHAIN_API_KEY`/`LANGCHAIN_PROJECT`(.env). 트레이싱은 이미 `@instrument`로 일부 연동됨.

> ### ✅ 현재 상태 (2026-06-09)
> - **8B 평가셋·채점기 이미 존재** — 채점기 `validation/eval.py:evaluate_prf`(rule별 P/R/F1, 테스트 9개 green), 라벨셋 `validation/benchmark.py` CASES + `tests/fixtures/labelset/`, 리포트 `validation/benchmark_report.md`. → **8E를 지금 바로 부분 시작 가능**(탐지 평가부터 LangSmith에 올림). 8C/8D 채점기는 나오는 대로 추가.
> - **langsmith 이미 설치됨** — 컨테이너 pytest 플러그인에 `langsmith-0.8.9` 확인 → 새로 add 불필요.
> - **⚠️ 키 필요** — `LANGCHAIN_API_KEY`(.env)가 있어야 실제 업로드 가능. 없으면 정직하게 skip(로컬 채점은 그대로 동작). **착수 전 키 확인.**
> - 8A latency 산출물(`bench/리포트_6탐지기_무키.md` 등)·`@instrument` trace_id 도 같은 LangSmith 프로젝트로 묶을 수 있음.

## 배경 (왜)
- 지금 평가가 스크립트별로 흩어져 있고 **시간에 따른 추적(회귀 감지)** 이 없다.
- LangSmith Datasets+Experiments+Evaluators 로 묶으면: 같은 평가셋에 코드가 바뀔 때마다 점수가 어떻게 변하는지 **한 곳에서** 보고, 8A 단계별 시간 트레이스도 같은 trace_id로 연결된다.

---

```
너는 우리 팀 플랫폼/관측 엔지니어다. 작업 디렉토리: C:\Users\user\Code-Shepherd\backend\m3
실행: docker compose m3 컨테이너(uv). LangSmith: .env 의 LANGCHAIN_API_KEY/LANGCHAIN_PROJECT 사용
(개발 중 프로젝트명에 본인 GitHub ID 포함 — 팀 규칙). 새 의존성: langsmith(이미 있으면 재사용).

[작업 방식]
- TDD로(테스트 먼저). superpowers:test-driven-development 사용. LangSmith 클라이언트는 seam 으로 분리해 mock(네트워크 없이 단위테스트).
- search-first 로 현재 LangSmith Datasets/Experiments/Evaluators API를 먼저 확인(추측 금지).

[선행 점검 — 통합 전 "각 채점기가 멀쩡한가" 먼저 ★]
LangSmith로 묶기 전에 로컬 채점기가 각각 정상이어야 한다:
- 8B(탐지 P/R/F1)·8C(코멘트 judge)·8D(RAGAS) 채점기를 각각 단독 실행해 정상 점수가 나오는지 확인.
- 어느 하나라도 깨졌거나 미완이면, 그건 빼고(있는 것만) 통합하거나 멈추고 보고.
  깨진 채점기를 LangSmith에 올려 가짜 점수를 추적하지 말 것.

[배경/문제]
8B(탐지 P/R/F1)·8C(코멘트 LLM-judge)·8D(RAG RAGAS) 채점기가 따로 논다. 추적·비교가 어렵다.

[목표]
1. Dataset 등록: 8B/8C/8D 의 라벨셋을 LangSmith Dataset(입력=PR/이슈, 기대=정답)으로 업로드하는 스크립트.
   - 시작점 = 8B 라벨셋(validation/benchmark.py CASES + tests/fixtures/labelset/) — 이미 있으니 이걸 먼저 Dataset 으로.
2. Experiment 실행: m3 에이전트(분석/코멘트/RAG)를 Dataset에 돌려 결과를 Experiment로 기록.
3. Evaluator 연결: 기존 채점기를 LangSmith custom evaluator 로 래핑 —
   - 탐지: rule별 Precision/Recall/F1 (8B 재사용),
   - 코멘트: verdict 일치 + LLM-judge 루브릭 (8C 재사용),
   - RAG: RAGAS context precision/recall·faithfulness (8D 재사용).
4. 대시보드 확인: Experiment별 점수가 LangSmith에 보이고, 코드 변경 시 회귀(점수 하락)가 추적되는지.
5. (선택) 8A 단계별 latency trace 를 같은 프로젝트/trace_id로 연결해 "품질+성능"을 한 화면에.

[반드시 지킬 것 — 합격 기준]
- 키 없음/네트워크 불가 시 정직하게 "skip(사유)" + 로컬 채점은 그대로 동작(LangSmith는 부가). 가짜 업로드 금지.
- 어떤 평가셋·어떤 evaluator가 등록됐는지 리포트에 명시. 1커맨드 재실행.
- 8B/8C/8D 채점 로직을 복붙·재구현하지 말 것 — 그 함수를 그대로 호출(중복 금지).

[TDD]
- evaluator 래퍼 단위테스트: 가짜 예측/정답 → 기존 채점기 호출 → LangSmith 포맷 점수로 변환 검증.
- LangSmith 클라이언트 mock: dataset 업로드/experiment 기록 호출 인자 검증(네트워크 없이).

[끝나면]
- [등록한 Dataset/Experiment/Evaluator 목록 / LangSmith 링크 또는 스크린샷 / 무엇이 추적되나 / 한계] 정리.
- 발표자료에 "LangSmith로 성능평가를 상시 추적 중"을 보여줄 링크 하나 확보.
- 막히면 멈추고 물어봐라.
```

---

## 참고 (사용자용 메모)
- 이건 **마지막 캡스톤** — 앞 세션(8B/8C/8D)이 만든 채점기를 LangSmith로 "묶기"만 합니다. 새 평가 로직을 또 만들지 않아요.
- 발표 임팩트: "성능평가를 1회성으로 한 게 아니라 **LangSmith에 데이터셋·실험·점수로 상시 추적**한다" → 운영 성숙도 어필.
- **8B 가 이미 끝났으니 8E를 바로 부분 시작 가능**(탐지 P/R/F1 부터 LangSmith에 올리고, 8C/8D 는 나오는 대로 추가). 단 LANGCHAIN_API_KEY 가 있어야 실제 업로드됨.
