# contracts/ — 계약 스키마 (수정 금지 · 게이트 2)

> **이 디렉토리는 정현 승인 후 동결된다. 테스트가 실패하면 코드를 고친다 — 계약을 고치지 않는다.**
> 변경이 필요하면 [결정요청] 패키지를 제출하고 명시적 승인을 받은 뒤에만 수정한다 (무응답 진행 금지).
> 현재 상태: **`SCHEMA_VERSION = 1.0.0` 동결됨** (게이트 2 승인: 정현, D1 2026-06-12 — Finding 추가 필드 rule_quote·file·reasoning 포함 승인).

## 파일

- `schemas.py` — 단일 진실 공급원. ReviewInput / ReviewOutput / ReviewState / Finding / Chunk / Concept / GapReport / GoldenLabel.

## 외부 인터페이스 (팀 합의 — 브리프 §1.2, MVP 중 변경 없음)

- 입력: `{diff: str, file_paths: list[str], repo_meta: dict}`
- 출력: `{findings: list[Finding], comment_md: str, gap_report: dict | null}`

## 노드 I/O 계약 (브리프 §3 — 이 표가 곧 단위테스트 명세)

| # | 노드 | 입력 (State 필드) | 출력 (State 필드) | 단위테스트 기준 |
|---|---|---|---|---|
| ⓪ | assemble_input | diff, file_paths, repo_meta | pr_context | 샘플 payload → 스키마 검증 통과 |
| ① | extract_concepts | pr_context | concepts, queries | 고정 diff → 핵심 개념 1개 이상 + 동의어 3개 |
| ② | retrieve | queries | chunks (top-k 5/query, dedup) | 시드 코퍼스에서 정답 rule_id 검색됨 |
| ③ | check_sufficiency | chunks, pr_context | route (+ requery_count) | 빈 결과 → gap, 정답 포함 → proceed |
| ④ | judge | chunks, pr_context | findings | 위반 PR → violation, 정상 PR → no_violation |
| ⑤ | compose_comment | findings 또는 gap | comment_md / gap_report | rule_id 인용 + 인용 문구가 코퍼스에 실존 |

추가 불변 조건:
- ③ requery 는 전 파이프라인 합산 **최대 1회** — `requery_count` 카운터가 State 에 있다.
- ④ judge 는 단일 CoT 프롬프트 안에 [검사계획 → 조항-코드 대조 → 오탐 점검] 3단계 포함. 노드를 쪼개지 않는다.
- `Finding.rule_quote` 는 인용한 Chunk.text 에, `Finding.evidence_lines` 의 각 줄은 diff 에 **string-match** 되어야 한다 (하네스 환각 검증 대상).

## 골든셋 라벨 스키마 (golden/pr_NNN/label.yaml — 게이트 1)

```yaml
expected: [{rule_id: CONV-API-001, verdict: violation}]  # 위반 PR
expected: []                                             # 정상 PR
expected: gap                                            # 지침공백 PR
```
