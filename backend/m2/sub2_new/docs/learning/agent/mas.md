# MAS (Multi-Agent System) 학습 노트

**날짜**: 2026-05-22
**복습 예정**: D+1, D+3, D+7

---

## 한 줄 요약
여러 전문가 직원을 고용해서 각자 맡은 일만 하게 하는 구조.

---

## 1. 비유
음식점에 비유하면:
- **단일 에이전트**: 주방장 1명이 주문받고, 요리하고, 서빙까지 다 함 → 느리고 실수 많음
- **MAS**: 홀 직원(주문) + 요리사(요리) + 서버(서빙)로 역할 분리 → 빠르고 전문적

Dev 2에서는:
- **StaticAnalysisAgent**: Pylint/radon만 담당하는 직원
- **SecurityScanAgent**: Bandit/Semgrep만 담당하는 직원
- 둘이 **동시에** 일함 → 합쳐서 결과 반환

---

## 2. 개념
> 하나의 복잡한 작업을 **여러 에이전트가 분담**해서 처리하는 시스템.
> 각 에이전트는 독립적으로 동작하고, 결과를 합산하거나 순서대로 전달한다.

**MAS 패턴 종류** (PRD에 나온 것들):

| 패턴 | 설명 | Dev 2에서 |
|------|------|----------|
| Parallel Independent | 동시 실행, 서로 독립 | StaticAnalysis + SecurityScan 동시 실행 |
| Supervisor | 상위 에이전트가 하위를 지시 | Dev1 오케스트레이터 |
| Aggregator | 여러 결과를 하나로 합침 | Dev4 평가 에이전트 |
| Cyclical Feedback Loop | 결과가 다시 입력으로 돌아옴 | Dev5 피드백 루프 |

---

## 3. 왜 쓰나
- **없으면**: 하나의 에이전트가 정적 분석 + 보안 스캔 + LLM 판단을 순서대로 → 느림
- **있으면**: 병렬로 동시 실행 → PRD 목표 "60초 이내 PR 코멘트" 달성 가능

---

## 4. 코드 (Dev 2)

```python
# agent.py — Dev 2의 MAS 진입점
import asyncio

async def run_dev2(payload: dict) -> list[dict]:
    # 두 에이전트를 동시에 실행 (Parallel Independent 패턴)
    results = await asyncio.gather(
        run_static_analysis(payload),  # StaticAnalysisAgent
        run_security_scan(payload),     # SecurityScanAgent
        return_exceptions=True          # 하나 실패해도 나머지 반환
    )
    return [r for r in results if not isinstance(r, Exception)]
```

---

## 복습 퀴즈

1. Q: MAS에서 Parallel Independent 패턴은 무엇인가?
   A: (두 에이전트가 서로 독립적으로 동시 실행되는 패턴)

2. Q: Dev 2에서 두 에이전트를 병렬 실행하는 Python 함수는?
   A: (asyncio.gather)

3. Q: 단일 에이전트 대신 MAS를 쓰는 이유는?
   A: (속도 향상 + 역할 분리로 유지보수 편리)
