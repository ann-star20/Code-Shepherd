---
description: LLM 호출 토큰 사용량을 점검하고 컨텍스트 엔지니어링 최적화 전략을 안내합니다.
---

LLM API 호출 비용을 점검하고 최적화합니다.

## 사용법

`/cost-check`

LLM 호출이 포함된 코드를 작성하거나 수정한 후 실행.

---

## 실행 순서

### Step 1 — 현재 토큰 사용량 측정

`src/agents/prompts/context_builder.py`의 `count_tokens()` 함수로 현재 프롬프트 토큰 수 확인:

```python
from src.agents.prompts.context_builder import count_tokens, build_personalization_context

# 샘플 데이터로 토큰 측정
ctx = build_personalization_context(
    feeds=sample_feeds,      # 실제 피드 10개
    profile=sample_profile,
    history=sample_history
)
print(f"현재 토큰 수: {ctx['tokens']}")
```

### Step 2 — 절감 전략 체크리스트

아래 항목 중 적용 안 된 것 확인:

- [ ] **피드 content truncation** — 각 피드 `content`를 200자로 제한했는가?
- [ ] **히스토리 슬라이딩 윈도우** — `user_history` 최근 5개만 넘기는가?
- [ ] **프로필 최소화** — 불필요한 필드 없이 `{level, industry, job}`만 넘기는가?
- [ ] **Redis 캐시 우선** — 캐시 히트 시 LLM 호출을 완전히 스킵하는가?
- [ ] **토큰 로거** — 매 호출마다 `input_tokens`, `output_tokens` 기록하는가?

### Step 3 — Before/After 비교

최적화 전후 토큰 수를 기록:

| 항목 | 최적화 전 | 최적화 후 | 절감률 |
|---|---|---|---|
| 피드 10개 포함 프롬프트 | ? tokens | ? tokens | ?% |
| 월간 예상 비용 | $? | $? | $? |

### Step 4 — 로그 확인

```bash
# 최근 LLM 호출 토큰 로그 확인
grep "token_usage" logs/app.log | tail -20
```

---

## 토큰 절감 기준값

| 전략 | 기대 절감 |
|---|---|
| content 200자 truncation | ~60% |
| 히스토리 슬라이딩 윈도우 | ~30% |
| Redis 캐시 우선 | 동일 쿼리 100% |

목표: Claude Haiku 기준 호출당 평균 1,000 input tokens 이하 유지.
