# SESSION 8-0a — LLM 복구: google.generativeai → google.genai (VS Code 복붙용)

> **시스템 완성 3단계 중 1번째. 8-0b·8-0c·8A~8E 모두보다 먼저.** (순서: 8-0a → 8-0b → 8-0c → 평가)
> 목적: 죽어 있는 LLM 경로를 살린다. `google.generativeai`(공식 지원종료)로 컨테이너에서 호출이 깨져 "왜 한 줄"이 규칙기반 폴백 중 → 신 SDK `google.genai`로 교체해 실제 Gemini 문장을 받는다.
> 범위: `google.generativeai`를 import 하는 **모든 모듈**(전수 확인). 평가·탐지기연결·RAG는 건드리지 않음(각각 8-0b·8-0c·8B~8D).
> 선행: 없음(최우선 1번). 단 8A 인수인계의 conftest 수집버그 선조치는 여기서 같이.

## 배경 (왜 먼저)
- 데모에서 코멘트 "왜 한 줄"이 규칙기반으로 나왔다. 원인: `google.generativeai` 패키지 **공식 지원종료(deprecated)** → 컨테이너 import/호출 실패. **Gemini 키 자체는 유효**(REST 200 확인).
- 다음 세션(8-0b)에서 연결할 TEST-003·PERF-003도 **LLM 기반**이라, LLM이 살아 있어야 그 탐지기들이 제대로(휴리스틱 폴백이 아니라) 동작한다. → **LLM 복구를 제일 먼저.**

---

```
너는 우리 팀 백엔드/LLM 엔지니어다. 작업 디렉토리: C:\Users\user\Code-Shepherd\backend\m3
실행 환경: docker compose 의 m3 컨테이너(uv). 테스트는 컨테이너 안에서 uv run --extra test pytest.
LLM=Gemini(.env GOOGLE_API_KEY, 유효 확인됨). ※ Anthropic 아님 Gemini.

[작업 방식]
- TDD로(테스트 먼저). superpowers:test-driven-development 스킬 사용.
- 변경은 최소(surgical)·동작 동등성 우선. search-first 로 신 SDK(google.genai) 호출 형태를 먼저 확인(추측 금지).

[선행 점검]
- (8A 인수인계) test-performance-agent/tests/conftest.py 에 collect_ignore_glob = ["fixtures/*"] 먼저 추가
  (fixtures/ 라벨 레포 자체 test 가 pytest 수집을 깨뜨림: ModuleNotFoundError: No module named 'src').
- pr-comment-agent 기존 테스트 green 확인(refine·verdict·aggregator).
- 현재 refine 이 규칙기반으로 폴백 중인지 로그로 확인(교체 전 상태 기록).

[목표 — SDK 교체]
- `import google.generativeai as genai` 를 쓰는 모든 곳을 신 SDK `from google import genai` 로 교체.
  search-first 로 전수 확인(최소: pr-comment-agent/llm_refiner.py, test-performance-agent/enrich/code_context.py,
  test_verification/edge_cases.py, performance/memory_leak.py — 더 있는지 grep 으로 확인).
- generate_content 호출 형태·응답 파싱을 신 SDK 에 맞춘다.
- 키 없음/네트워크 실패 시 기존 휴리스틱 폴백은 그대로 유지(정직).

[반드시 지킬 것 — 합격 기준]
- 컨테이너에서 refine 이 실제 LLM "왜 한 줄"을 반환(폴백 아님)하는 걸 로그/테스트로 확인.
- 기존 테스트 전부 여전히 green(회귀 0). 교체 분은 테스트로 못박음.
- 가짜 LLM 문장 금지(미가용 시 정직하게 폴백).

[TDD]
- _call_llm seam mock → LLM 경로 사용 / 실패 시 휴리스틱 폴백, 둘 다.

[끝나면 — 8-0b 로 인수인계]
- [교체한 파일 목록 / refine 이 실제 LLM 반환하는지(로그) / 회귀 테스트 결과] 정리.
- 다음(8-0b): 6탐지기 연결 — 그때 edge_cases·memory_leak 이 이 세션 덕에 LLM 모드로 동작함.
- 막히면 멈추고 물어봐라.
```

---

## 참고 (사용자용 메모)
- 3단계(완성) 중 **1번째·제일 먼저**. LLM을 살려야 다음 세션에서 연결할 두 탐지기(엣지케이스·메모리누수)가 제대로 돌아요.
- 핵심 발견: LLM이 안 도는 건 **키 문제가 아니라 옛 패키지(지원종료)** 때문 → 이 교체가 그걸 고칩니다.
