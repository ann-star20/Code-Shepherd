# 하네스 엔지니어링 + LangSmith + Repository 패턴 학습 노트

**날짜**: 2026-06-04
**관련 파일**: `sub2_new/dev2/db.py`, `common/harness.py` (미생성)
**복습 예정**: D+1, D+3, D+7

---

## 1. LangSmith 연동

### 한 줄 요약
에이전트 실행 흐름을 자동으로 CCTV처럼 기록해두는 관찰 도구.

### 왜 쓰나
- LLM 어디서 느려졌는지, 어디서 틀렸는지 웹 대시보드에서 확인 가능
- `print` 디버깅 없이 전체 흐름을 시각적으로 추적

### 실제로 하는 일 (.env에 추가만 하면 끝, 코드 수정 없음)
```bash
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__실제키    # langsmith.com에서 발급
LANGCHAIN_PROJECT=dev2-wooya   # 본인 GitHub ID 붙이기
```

### 주의사항
- LANGCHAIN_PROJECT는 반드시 본인 ID 포함 (예: dev2-wooya)
- 팀원과 같은 프로젝트명 쓰면 trace가 섞임

---

## 2. common/harness.py

### 한 줄 요약
에이전트 여러 개를 동시에 실행하고, 30초 타임아웃/실패를 자동 처리하는 공통 유틸리티.

### 왜 쓰나
없으면 Dev2, Dev3가 각자 타임아웃/DB 로깅을 중복 구현해야 함.

### 구현해야 할 핵심 함수
```python
# common/harness.py — 현재 파일 없음, 만들어야 함

async def run_parallel_agents(agents, db_pool, pr_trace_id, task_id):
    """에이전트 목록을 asyncio.gather로 병렬 실행. 30초 타임아웃 자동 처리."""
    ...

def make_timeout_result(agent_name: str) -> dict:
    """타임아웃 발생 시 반환할 기본 Output Contract."""
    return {
        "task_id": "",
        "agent": agent_name,
        "issues": [],
        "summary": {"critical": 0, "major": 0, "minor": 0},
        "execution_ms": 30000,
        "error": "timeout"
    }
```

### 타임아웃 처리 주의사항 (CLAUDE.md §6)
```python
# 올바른 패턴 — try/except가 async with 바깥에 있어야 함
try:
    async with AgentHarness(...) as harness:
        return await harness.run(fn, *args, **kwargs)
except asyncio.TimeoutError:
    return make_timeout_result(agent_name)

# 잘못된 패턴 — __aexit__이 성공으로 판단해서 DB에 success로 기록됨
async with AgentHarness(...) as harness:
    try:
        return await harness.run(fn, *args, **kwargs)
    except asyncio.TimeoutError:   # ← 여기서 잡으면 안 됨
        return make_timeout_result(agent_name)
```

---

## 3. Repository 패턴

### 한 줄 요약
DB SQL을 에이전트 로직과 분리해서 db.py 한 곳에 모아두는 구조.

### 왜 쓰나
- 에이전트 코드에 SQL이 없으면 테스트할 때 DB 없이도 Mock으로 대체 가능
- SQL 변경 시 db.py만 수정하면 됨

### 현재 상태 — 이미 적용됨 ✅
```python
# sub2_new/dev2/db.py
# 에이전트가 직접 SQL 안 씀. db.py 함수만 호출.
await insert_scan_issues(scan_id, issues, agent)
await insert_scan_execution(task_id, pr_id, ...)
await insert_scan_summary(scan_id, agent, summary)
```
→ 추가 작업 불필요.

---

## 실제 작업 우선순위

| 항목 | 상태 | 다음 액션 |
|------|------|---------|
| LangSmith 연동 | 🔴 키 미설정 | langsmith.com에서 API 키 발급 후 .env 추가 |
| common/harness.py | 🔴 파일 없음 | run_parallel_agents + make_timeout_result 구현 |
| db.py Repository 패턴 | ✅ 완료 | 없음 |

---

## 복습 퀴즈

1. Q: LangSmith 연동할 때 .env에 추가해야 할 변수 3개는?
   A: (LANGCHAIN_TRACING_V2, LANGCHAIN_API_KEY, LANGCHAIN_PROJECT)

2. Q: 타임아웃 처리 시 try/except를 async with 안에 쓰면 안 되는 이유는?
   A: (__aexit__이 예외를 못 보고 DB에 status='success'로 잘못 기록됨)

3. Q: Repository 패턴의 핵심 규칙은?
   A: (에이전트 코드에 SQL 직접 노출 금지, db.py 함수로만 접근)
