# m3 '왜 한 줄' 코멘트 품질 — LLM-as-judge (SESSION 8C)

생성일: 2026-06-09
judge 모델: `gemini-2.5-flash-lite`  (JUDGE_MODEL 로 교체 가능)
케이스 수: 5건 (verdict 라벨셋 이슈 케이스 + skill 변형)
피평가 '왜 한 줄' 생성: LLM 0건 / 휴리스틱 5건

## 루브릭 (각 축 1~5)
- **consistency**: 판정(verdict)과의 정합성 — 한 줄이 판정과 모순되지 않는가
- **actionable**: 도움됨 — 무엇을/왜 고쳐야 하는지 실천적 단서를 주는가
- **tone**: 톤 — 대상 개발자 수준(junior/mid/senior)에 적합한가
- **no_hallucination**: 환각 없음 — 이슈 목록에 없는 사실을 지어내지 않는가

## 결과: ⏭️ SKIP — 전 케이스 judge 미가용 — 가짜 점수 금지(정직 skip).

> 정직 원칙상 가짜 점수를 만들지 않는다. judge LLM 가용 시 아래 1커맨드로 재실행:
> ```
> cd /app/service/pr-comment-agent && \
>   LLM_MODEL=gemini-2.5-flash-lite uv run python validation/comment_judge.py
> ```

skip 케이스 5건 (사유 동일: judge 미가용/쿼터).