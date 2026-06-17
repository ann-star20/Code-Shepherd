# Harness 빠른 시작 가이드

> **Harness/LangSmith 전체 규칙** → [`docs/GLOBAL_AGENT_RULE.md §7~8`](GLOBAL_AGENT_RULE.md)  
> **Trace ID 체계 / Timeout 처리 상세** → [`CLAUDE.md §3`](../CLAUDE.md)

---

## 필수 환경변수

```bash
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__xxxx
LANGCHAIN_PROJECT=module{N}-{yourGitHubId}   # GitHub ID 필수
```

---

## AgentHarness 기본 패턴

```python
from common.harness import AgentHarness

# 단일 에이전트
try:
    async with AgentHarness(
        agent_name="MyAgent",
        trace_id="pr_3a9f1c2b44e0",
        task_id=state["task_id"],
        db_pool=pool,
    ) as harness:
        result = await harness.run(my_agent_fn, state)
except asyncio.TimeoutError:
    return make_timeout_result("MyAgent")   # with 블록 바깥에서 처리
```

```python
from common.harness import run_parallel_agents

# 병렬 에이전트 (Module 2 + 3)
results = await run_parallel_agents(
    agents=[
        ("static_analysis", sa_graph.ainvoke, (state,), {}),
        ("security_scan",   ss_graph.ainvoke, (state,), {}),
    ],
    db_pool=pool,
    pr_trace_id=pr_trace,
    task_id=state["task_id"],
)
```

---

## PR에 첨부할 최소 기록

```
- trace_id:  (LangSmith trace URL 또는 ID)
- score:     (품질 점수, 해당 없으면 생략)
- status:    success | failed | hitl_required
```

---

## 체크리스트

```text
□ LANGCHAIN_PROJECT에 본인 GitHub ID 포함
□ AgentHarness로 모든 에이전트 실행 래핑
□ TimeoutError는 async with 블록 바깥에서 처리
□ PR description에 trace_id 또는 LangSmith URL 첨부
□ Mock 모드(USE_MOCK_LLM=true)에서도 Harness 기록 동작 확인
```
