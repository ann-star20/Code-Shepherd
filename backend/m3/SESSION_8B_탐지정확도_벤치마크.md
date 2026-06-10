# SESSION 8B — 탐지 정확도: 벤치마크 확장 + rule별 P/R/F1 (VS Code 복붙용)

> 목적: 골든 라벨을 **1건(5이슈) → 다건(양성+음성)** 으로 확장하고, 채점기를 **rule별 Precision/Recall/F1**로 업그레이드한다.
> 범위: `test-performance-agent/validation/eval.py` + `tests/fixtures/`(라벨셋). 탐지기 로직은 건드리지 않음(평가만).
> 선행: **8-0b(6탐지기 연결) 완료 후**. 탐지기 6개가 파이프라인에 연결된 상태에서 골든라벨을 **6탐지기 기준**으로 잡아야 한다(4개로 잡으면 연결 후 다시 해야 함). 기존 eval.py(recall·false_alarm)·expected_output.json 패턴을 확장.

> ### ✅ 이미 구현·검증됨 (2026-06-09 — 메인 세션에서 완료) — 새 창에서 다시 실행하지 말 것(중복)
> - 채점기 `validation/eval.py:evaluate_prf` (rule별 P/R/F1) + settings `OVERALL_F1_PASS_THRESHOLD`/`RULE_F1_MIN_THRESHOLD`
> - TDD 테스트 `tests/test_task18_prf_scorer.py` (9개 RED→GREEN)
> - 라벨셋 `tests/fixtures/labelset/`(perf_case·memleak_case·clean_case·edge_fp_case) + 러너 `validation/benchmark.py`
> - 실측 리포트 `validation/benchmark_report.md` — **전체 F1 0.966 PASS, 미탐 0, TEST-003 오탐 1건 정직 노출**. 회귀 306 green.
> 아래 프롬프트는 기록·근거용. **다음은 8C.**

---

## ⚠️ 8A 인수인계 — 착수 전 먼저 읽기

8A(시스템 성능 계측)에서 부딪힌 문제 중, **8B에서 반드시 더 커지는 것** 하나가 있다:

1. **[필수 선조치] pytest가 fixture 레포의 자체 테스트를 수집하다 깨진다.**
   - `test-performance-agent/tests/fixtures/sample_repo/tests/test_posts.py` 가 `ModuleNotFoundError: No module named 'src'` 로 수집 단계에서 죽는다.
   - 루트 `backend/m3/pyproject.toml` 의 `addopts="--ignore=tests/fixtures"` 는 **`backend/m3/tests/fixtures` 만** 막고, **`test-performance-agent/tests/fixtures` 는 안 막는다.**
   - **8B는 fixtures/ 에 라벨 케이스(자체 test 파일 포함)를 5개+ 추가하므로 이 문제가 폭증한다.**
   - 👉 **착수 첫 단계**: `test-performance-agent/tests/conftest.py` 에 아래 한 줄을 먼저 넣어라.
     ```python
     collect_ignore_glob = ["fixtures/*"]
     ```
     (이걸 안 하면 매번 `--ignore=test-performance-agent/tests/fixtures` 를 손으로 붙여야 한다.)

2. **환경 설정이 결과를 조용히 바꾼다 → 리포트에 박아라.** 8A는 컨테이너에 `RAG_ENABLED` 가 켜져 있어 "RAG: on" 으로 측정됐다(기본 off 가정과 어긋남). 8B는 정확도라 RAG/LLM enrich 가 탐지 결과 자체를 바꾸진 않지만(컨텍스트 필드만 채움), **어떤 설정에서 쟀는지(USE_MOCK_LLM·RAG_ENABLED·Gemini 모델)를 리포트에 명시**해야 신뢰가 선다.

3. **8A의 honesty 원칙 = 8B의 "가짜 정답 금지".** 8A는 "측정 못 한 단계는 빈칸(가짜 0 금지)". 8B의 대응: **라벨(정답)을 탐지기 출력으로 자동 생성하면 순환논리**(탐지기가 자기 채점에서 100점) → 사람이 확정한 정답만 써라.

4. **측정 전 선행 점검 먼저.** 8A는 289개 테스트 green 확인 후 쟀다. 8B도 동일 — 탐지기 단위테스트 green + 기존 eval.py 1회 정상 채점 확인 후 점수를 내라.

---

## 배경 (왜)
- 현재 eval.py는 골든 1건으로 recall 100%·오탐 0%를 낸다. **표본 1개·음성 케이스 없음·rule별 분해 없음** → "제대로 된 성능평가"라 부르기 약하다.
- 정직하게 강해지려면: (a) 라벨 PR을 늘리고, (b) **깨끗한 코드(이슈 0이어야 정상=음성)** 도 넣어 오탐을 진짜로 검증하고, (c) **6개 rule(TEST-001/003/004·PERF-001/002/003)별로** P/R/F1을 쪼갠다. ※ 8-0에서 TEST-003·PERF-003도 연결됐으므로 라벨·채점에 포함.

---

```
너는 우리 팀 백엔드 엔지니어다. 작업 디렉토리: C:\Users\user\Code-Shepherd\backend\m3\test-performance-agent
테스트(pytest): 컨테이너 안에서 uv run --extra test pytest. 평가 스크립트: validation/eval.py 확장.

[작업 방식]
- TDD로(테스트 먼저). superpowers:test-driven-development 사용.
- 기존 eval.py 의 (rule_id, file) 멀티셋 매칭·골든라벨 패턴을 따른다(line은 참고값). 새 채점 로직은 테스트로 못박는다.

[선행 점검 — 평가 전 "탐지기가 멀쩡한가" 먼저 ★]
정확도를 재기 전에 탐지기 자체가 정상이어야 한다:
- (8A 인수인계) tests/conftest.py 에 `collect_ignore_glob = ["fixtures/*"]` 먼저 추가 —
  fixtures/ 의 라벨 레포 자체 test 파일이 pytest 수집을 깨뜨린다(ModuleNotFoundError: No module named 'src').
  안 하면 매 실행 `--ignore=test-performance-agent/tests/fixtures` 를 손으로 붙여야 한다.
- 탐지기 단위테스트 전부 green 확인(coverage/missing_funcs/nplus1/complexity + test_task7 등).
- 기존 eval.py(골든1건)가 지금도 정상 채점되는지 1회 실행(recall/false_alarm 산출 확인).
- 명백한 탐지 버그(같은 줄 중복 오탐·정상 코드 오탐·확실한 누락)가 보이면 멈추고 보고 —
  버그를 라벨로 굳히면 평가가 거짓이 된다. 라벨 위에서 점수 내기 전에 탐지부터 신뢰 확보.

[배경/문제]
eval.py 는 전체 recall·false_alarm 만 낸다. 표본이 1개라 신뢰가 약하고 rule별 강·약점을 모른다.
또 "깨끗한 코드인데 오탐을 내는가"(음성 케이스)를 검증하지 않는다.

[목표]
1. 라벨셋 확장: tests/fixtures/ 에 라벨 PR 케이스를 최소 5개로 늘린다.
   - 양성: 일부러 TEST-001/TEST-004/PERF-001/PERF-002 를 유발하는 코드 + expected_output.json(정답).
   - 음성: 이슈가 없어야 정상인 깨끗한 코드 케이스(expected = 0건) 최소 1~2개.
   - 데모 레포(-dev3-demo PR #1~#4)의 실제 결과를 라벨로 고정해도 됨(사람이 정답 확정).
2. 채점기 업그레이드: rule별 + 전체로 Precision / Recall / F1 산출.
   - Precision = matched / total_output, Recall = matched / total_expected, F1 = 조화평균.
   - rule별(TEST-001/003/004·PERF-001/002/003) 표 + 전체 행. 음성 케이스의 오탐(FP)도 합산.
   - ※ TEST-003·PERF-003은 LLM/휴리스틱 기반이라 오탐이 많을 수 있다 → rule별 표가 그걸 정직하게 드러내야 한다(낮으면 낮다고).
3. FP/FN 리스트: 틀린 케이스(헛다리·놓침)를 rule·파일과 함께 출력(원인 분석용).
4. 합격선/회귀 기준선: 전체 F1·rule별 최소선을 settings 에 두고 PASS/FAIL 판정(기존 recall≥0.9·오탐≤0.1 계승·세분화).

[반드시 지킬 것 — 합격 기준]
- 라벨(정답)은 사람이 확정한 값만. 탐지기 출력으로 정답을 자동 생성하지 말 것(순환·가짜 금지).
- 표본 수·케이스 목록을 리포트에 명시. 음성 케이스 최소 1개 포함.
- 1커맨드 재실행(uv run python validation/eval.py) + 결과 markdown 표 저장.

[TDD]
- 채점기 단위테스트: (가짜 outputs, 가짜 expected) → 기대 P/R/F1 검증(완전일치·일부일치·전부오탐·전부놓침).
- 음성 케이스(expected 0, output>0) → Precision 하락이 반영되는지.

[끝나면]
- [rule별·전체 P/R/F1 표 / 표본 수·케이스 / FP·FN 예시 / 합격여부 / 한계] 정리.
- 발표자료 §3(탐지 성능평가)에 꽂을 표 그대로 남겨라.
- 막히면 멈추고 물어봐라.
```

---

## 참고 (사용자용 메모)
- 발표 핵심: "골든 **1건**이 아니라 **양성+음성 N건**으로, **rule별 Precision/Recall/F1**까지 쪼개 측정했다"가 신뢰를 줍니다.
- 음성 케이스(깨끗한 코드인데 오탐 안 내는지)가 의외로 중요 — "헛소리 안 한다"의 증거예요.
