# SESSION 8C — 코멘트 품질: LLM-as-judge 평가 (VS Code 복붙용)

> 목적: 코멘트의 **verdict 정확도** + **"왜 한 줄" 품질**을 LLM-as-judge 루브릭으로 정량 평가한다.
> 범위: `pr-comment-agent`(llm_refiner·validation). 코멘트 **구조(표·📊·📖)는 코드 결정이라 평가 대상 아님** — 평가는 verdict와 LLM이 쓰는 정성 문장만.
> 선행: 없음(8-0a 이미 끝남). 이 세션은 LLM이 실제 동작함을 **검증**하고 **품질 채점만** 한다.

> ### ✅ 현재 상태 (2026-06-09 — 착수 전 실측 확인됨)
> - **8-0a(SDK 교체) 완료** — `google.generativeai`→`google.genai` 전수 교체됨(llm_refiner·code_context·edge_cases·memory_leak). → **아래 [0단계]는 이미 끝났다. 다시 교체하지 말고 "LLM이 실제로 도는지" 검증만 하라.**
> - **8-0b·8-0c·8A·8B 완료** — 탐지기 6개 연결·RAG 기본 ON·시스템 성능 실측·탐지 정확도(rule별 P/R/F1 전체 0.966) 끝. 컨테이너 테스트 306 green.
> - **⚠️ 쿼터 함정(실측 확인)** — 컨테이너 기본 모델 `gemini-2.5-flash`는 무료 1일 ~20회 → refine + LLM-judge 를 풀로 돌리면 **즉시 429**. **`LLM_MODEL=gemini-2.5-flash-lite` 로 오버라이드**(8B/8A 때 이 방식으로 429 회피 확인)하거나 케이스 수를 줄여라.
> - **8B 라벨셋이 이미 있다** — `validation/benchmark.py`의 CASES + `tests/fixtures/labelset/`(perf_case·memleak_case·clean_case·edge_fp_case) + 채점기 `validation/eval.py:evaluate_prf`. verdict/코멘트 평가에 **그대로 재사용**(새로 안 만듦).

## 배경 (왜)
- 데모에서 코멘트의 "왜 한 줄"이 규칙기반으로 폴백됐다. 원인 후보: **`google.generativeai` 패키지가 공식 지원 종료(deprecated)** — 컨테이너에서 import/호출이 깨질 수 있음(평가 실행 중 FutureWarning 확인). Gemini 키 자체는 유효(REST 200 확인).
- 코멘트 평가가 지금은 "verdict·개수 일치"(정답성)뿐 — **"좋은 코멘트인가(정확/도움/톤/환각0)"** 는 측정 안 함.

---

```
너는 우리 팀 백엔드/LLM 엔지니어다. 작업 디렉토리: C:\Users\user\Code-Shepherd\backend\m3
LLM=Gemini(키는 .env GOOGLE_API_KEY, 유효 확인됨). 실행: docker compose m3 컨테이너(uv).
※ Claude/Anthropic 아님 Gemini임. 단, LLM-as-judge 채점기는 모델 교체 가능하게 추상화.

[작업 방식]
- TDD로(테스트 먼저). superpowers:test-driven-development 사용. LLM 호출부는 seam 으로 분리해 mock.

[0단계 — LLM 경로 복구] ✅ 8-0a 에서 이미 완료 — 다시 교체하지 말 것.
- `google.generativeai`→`google.genai` 전수 교체 끝(llm_refiner·code_context·edge_cases·memory_leak).
- 이 세션에서 할 일은 "교체"가 아니라 "검증": 컨테이너에서 refine 이 실제 LLM 한 줄을 반환하는지 확인.
- ★ 검증·judge 실행 시 반드시 LLM_MODEL=gemini-2.5-flash-lite (기본 flash 는 1일 20회라 429 위험 — 실측 확인됨).
- 키 없음/실패 시 휴리스틱 폴백은 그대로 유지(정직).

[선행 점검 — 품질 평가 전 "코멘트 생성이 멀쩡한가" 먼저 ★]
품질 채점에 들어가기 전에:
- pr-comment-agent 기존 테스트 green 확인(refine 구조·verdict·aggregator·github_poster dry-run).
- 컨테이너에서 refine 이 실제 LLM "왜 한 줄"을 반환하는지 확인(flash-lite로) — 여전히 규칙기반으로 폴백하면
  LLM 품질 평가가 무의미하니 거기서 멈추고 원인(네트워크/키/쿼터) 보고.
- verdict 로직(escalate/rework/lgtm 임계값)이 기대대로 도는지 스모크 1회.

[목표 — 코멘트 품질 평가]
1. verdict 정확도(확장): 8B 라벨셋(validation/benchmark.py CASES + tests/fixtures/labelset/) 재사용 — 각 케이스에 사람이 기대 verdict(lgtm/rework/escalate)를 추가하고, aggregate 산출 verdict 와 일치율 측정.
2. "왜 한 줄" LLM-as-judge: 생성된 한 줄을 루브릭으로 1~5 채점.
   - 루브릭 축: (a) 판정과의 정합성, (b) 도움됨(actionable), (c) 톤(skill_level junior/mid/senior 적합),
     (d) 환각 없음(이슈에 없는 사실을 지어내지 않음).
   - judge 모델 호출은 추상화(seam) — mock 가능. 케이스 ≥10건.
3. 결과 표: verdict 일치율 + 루브릭 평균/항목별 점수 + 낮은 점수 사례.

[반드시 지킬 것 — 합격 기준]
- judge 프롬프트·루브릭을 코드/리포트에 명시(재현·검증 가능). judge=피평가 같은 모델이어도 무방하나 명시.
- LLM 미가용 시 평가는 "skip(사유)"로 정직하게 — 가짜 점수 금지.
- 케이스 수·judge 모델·루브릭을 리포트에 명시.

[TDD]
- 0단계: _call_llm seam mock → refine 이 LLM 한 줄을 쓰는 경로 / 실패 시 휴리스틱 폴백 둘 다.
- judge 채점기: 가짜 judge 응답(JSON 점수) → 집계·평균·항목별 표 검증. 빈 응답 → skip.

[끝나면]
- [LLM 실제 동작 검증(flash-lite, 폴백 아님 확인) / verdict 일치율 / 루브릭 점수표 / 케이스 수 / 한계] 정리.
- 발표자료 §3 품질평가(코멘트) 칸에 꽂을 표 남겨라(8A §3-1b·8B §3-1c 옆에).
- 막히면 멈추고 물어봐라.
```

---

## 참고 (사용자용 메모)
- 8-0a 가 옛 패키지(`google.generativeai` 지원종료) 문제를 **이미 고쳤습니다** → 이 세션은 SDK 교체가 아니라 "LLM이 실제로 도는지 확인 + 품질만 측정"입니다.
- **실측 함정**: 컨테이너 기본 모델 `gemini-2.5-flash`는 무료 1일 ~20회 쿼터라, judge 까지 돌리면 429 납니다. `LLM_MODEL=gemini-2.5-flash-lite` 로 돌리세요(8A/8B 때 이 방식으로 회피 확인).
- 코멘트는 "표 구조는 코드가, 한 줄 설명만 AI"라서 **평가도 그 한 줄에 집중**하면 됩니다(과하게 안 잡아도 됨).
- claude-api 스킬은 Anthropic용이라 여기선 불필요(우리는 Gemini). 단 LLM-judge 추상화는 나중에 모델 바꿀 때 편함.
