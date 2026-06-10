# SESSION 7D — (선택·후속) 코멘트에 지표 줄(커버리지·복잡도) (VS Code 복붙용)

> 목적: 코멘트의 **📊 커버리지 % · 최대 복잡도** 한 줄을 위해, 측정된 `metrics` 를 m3 `/verify`→`/review`→코멘트까지 흐르게 한다.

> ⚠️ **주의 — 이건 공유 계약을 건드릴 수 있음.** 지표는 상류(탐지기)에서 계산돼 `/verify` 응답을 타고 와야 하는데, 그 경계(`M3VerifyResponse`·`IssueItem`)가 공유 계약이다. 필드 추가가 필요하면 **additive·optional(기본값)** 로만, 그리고 `docs/MODULE_CONTRACT.md` 갱신 + 전 모듈 알림. → 그래서 **핵심(7A~7C) 다음 선택 작업**으로 둠. 데모상 RAG(📖)가 우선이고 지표는 보너스.

> 범위: m3 — (필드 추가 시) `_shared/contracts.py` + `app/main.py`(`_build_response`·`_collect_outputs`·`_review_*`) + 7C 렌더. + 관련 테스트.

> 선행: **7C**. (7A~7C 끝나고, 여유 있을 때만.)

---

```
너는 우리 팀 시니어 백엔드 엔지니어다. 작업 디렉토리: C:\Users\user\Code-Shepherd\backend\m3
테스트는 m3 가상환경 python으로: .venv\Scripts\python.exe -m pytest tests/test_review_endpoint.py pr-comment-agent/tests -q
(python.exe 는 Store 스텁이라 직접 호출 금지)

[작업 방식]
- tdd-workflow 스킬로 테스트부터(TDD는 항상). 외부의존 mock.
- 먼저 '공유 계약을 안 늘리고' 지표를 코멘트까지 보낼 길이 있는지 코드를 읽고 따져봐라(예: summary/metrics 재활용,
  /review 가 다시 계산 가능한지). 정말 필요할 때만 계약에 optional 필드를 additive 로 추가한다.

[배경/문제]
test_verification 탐지기는 coverage 등 metrics 를 계산하지만, /verify 응답(M3VerifyResponse)·IssueItem 에 실려
/review 까지 오지 않아 코멘트의 '📊 지표 줄'을 채울 값이 없다.

[목표]
코멘트 헤더 아래 '📊 커버리지 NN% · 최대 복잡도 NN' 한 줄을 실제 측정값으로 채운다.
- 1순위: 공유 계약 변경 없이(이미 오는 값/요약 활용) 가능한지.
- 불가하면: M3VerifyResponse 에 optional metrics(기본 None) 또는 IssueItem 에 optional metric_value 를 additive 로 추가.

[반드시 지킬 것 — 합격 기준]
- 계약 변경은 'optional + 기본값' 만(기존 호출자 회귀 0). 변경 시 docs/MODULE_CONTRACT.md 갱신 + PR description 에 '공유 계약 변경' 명시.
- 측정값 없으면 지표 줄을 정직하게 '생략'(0%·가짜 숫자 금지).
- 7C 코멘트 구조(표·📖) 회귀 0 — 지표 줄만 추가.

[TDD]
- metrics 가 있을 때 코멘트에 지표 줄이 뜨고, 없을 때 줄이 빠지는지.
- 계약에 필드 추가했다면 기존 verify/review 테스트 회귀 green.

[끝나면]
- [변경 파일 / 계약 변경 여부 / 테스트 결과] 정리. 계약 바꿨으면 알릴 모듈 명시.
- 막히면 멈추고 물어봐라.
```

---

## 참고 (사용자용 메모)
- 지표는 **"있으면 좋은" 보너스**라 맨 뒤·선택. RAG(📖)가 우선.
- 이건 **공유 계약(팀 공용 약속)을 건드릴 수 있어서** 팀 알림이 필요할 수 있음 → 그래서 핵심 다음에 따로.
- 급하면 **건너뛰어도** 데모는 됨(코멘트에 지표 줄만 빠짐).
