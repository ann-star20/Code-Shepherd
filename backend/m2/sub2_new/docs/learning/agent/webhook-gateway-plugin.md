# webhook-gateway 플러그인 아키텍처 학습 노트

**날짜**: 2026-06-02
**파일**: `dev2/webhook-gateway_2/registry.py`, `dev2/webhook-gateway_2/agents/dev2_adapter.py`
**복습 예정**: D+1, D+3, D+7

## 한 줄 요약
PR이 오면 등록된 분석 에이전트들이 자동으로 모두 호출되는 공용 파이프라인 — Dev2는 어댑터 파일 1개 + import 1줄만 추가하면 끼어들 수 있다.

## 왜? / 언제?
- **해결하는 문제**: 여러 에이전트(Dev2, Dev3...)가 각자 GitHub Webhook / PR 코멘트 등록을 따로 구현하면 중복·충돌 발생
- **적합한 상황**: 팀원이 병렬로 분석 모듈을 개발하고, 나중에 한 파이프라인에 합쳐야 할 때
- **부적합한 상황**: 분석 에이전트가 1개뿐이라 공용 게이트웨이가 불필요한 경우

## 전체 흐름
```
GitHub PR 오픈
    ↓
server.py  (Flask, Webhook 수신 + HMAC-SHA256 서명 검증)
    ↓
gateway.py (clone → diff 추출 → 등록된 에이전트 전부 호출 → 결과 합산 → 판정 → 코멘트)
    ├── dev3_adapter.py  →  test/performance 분석
    └── dev2_adapter.py  →  static/security 분석
```

## 핵심 코드 (우리 프로젝트)

### 플러그인 등록 — registry.py
```python
# @register 데코레이터 한 줄로 게이트웨이에 등록
@register("security_scan")
def analyze_security(ctx: PRContext) -> list[dict]:
    # ctx.work_dir: clone된 코드 경로
    # ctx.pr_diff:  unified diff
    return [{"severity": "Critical", "file": "src/auth.py", ...}]
```

### 자동 등록 트리거 — server.py
```python
# import 순간 @register가 실행됨 → 함수가 _AGENTS 리스트에 추가됨
import agents.dev2_adapter
```

### 게이트웨이가 전부 호출 — gateway.py
```python
for agent in registered_agents():
    issues += agent.fn(ctx)   # dev2, dev3 둘 다 여기서 호출
```

## 핵심 개념 3가지
1. **플러그인 패턴**: 기존 코드 수정 없이 새 기능을 추가할 수 있는 구조. `import` 한 줄 = 플러그인 장착.
2. **데코레이터 사이드이펙트**: `@register("이름")`은 함수 정의 시점에 전역 리스트에 함수를 등록한다. 호출 안 해도 등록됨.
3. **PRContext**: 게이트웨이가 clone/diff를 대신 처리하고 에이전트에게 `work_dir`, `pr_diff`만 전달 — 에이전트는 분석만 담당.

## 복습 퀴즈
1. Q: `import agents.dev2_adapter`만 해도 에이전트가 등록되는 이유는?
   A: (모듈 import 시 `@register` 데코레이터가 실행되어 `_AGENTS` 전역 리스트에 자동 추가되기 때문)

2. Q: `ctx.work_dir`과 `ctx.pr_diff`는 누가 채워주나?
   A: (gateway.py가 GitHub clone + diff 추출 후 PRContext에 채워서 각 에이전트에 전달)

3. Q: Dev2 어댑터에서 DB 저장이나 GitHub 코멘트를 하면 안 되는 이유는?
   A: (gateway.py가 이미 담당 — 어댑터가 하면 중복 등록되고 역할이 섞임)
