---
description: 새로운 기능, 컴포넌트, 에이전트, 스킬, API 등이 추가될 때 5개 핵심 문서를 일괄 업데이트합니다.
---

새로운 것이 추가되었을 때 아래 5개 문서를 순서대로 검토하고 업데이트합니다.

## 업데이트 대상 문서

| 문서 | 경로 | 업데이트 기준 |
|------|------|-------------|
| 기획 설계 | `docs/plans/2026-04-30-3rd-project-sub2-design.md` | 기능 목적·범위·컴포넌트 구조가 바뀔 때 |
| 도구 가이드 | `docs/claude-tools-guide.md` | 새 에이전트·스킬·커맨드가 추가될 때 |
| 아키텍처 | `docs/architecture_allguzo.md` | 서비스·컴포넌트·데이터 흐름이 바뀔 때 |
| 요구사항 | `docs/requirements.md` | 기능 요구사항 항목이 추가·변경될 때 |
| 워크플로우 | `docs/workflow_apiflow.md` | 사용자 여정·시스템 플로우·화면이 바뀔 때 |

---

## 실행 순서

**사용법**: `/update-docs [추가된 것의 설명]`
예: `/update-docs RagasDashboard 컴포넌트 추가`
예: `/update-docs /harness/ragas API 엔드포인트 추가`
예: `/update-docs silent-failure-hunter 에이전트 추가`

---

### Step 1 — 추가된 내용 파악

추가된 것이 아래 중 어느 유형인지 확인:
- **UI 컴포넌트** → design.md, architecture_allguzo.md, requirements.md, workflow_apiflow.md 업데이트
- **API 엔드포인트** → architecture_allguzo.md, requirements.md, workflow_apiflow.md 업데이트
- **에이전트** → guide.md, design.md(에이전트 목록 섹션) 업데이트
- **스킬** → guide.md 업데이트
- **커맨드** → guide.md 업데이트
- **DB 스키마 변경** → architecture_allguzo.md, requirements.md(DB 스키마 섹션) 업데이트
- **새 서비스/패키지** → architecture_allguzo.md(인프라 표), requirements.md(기술 스택) 업데이트

### Step 2 — 5개 문서 순서대로 읽기

```
1. docs/plans/2026-04-30-3rd-project-sub2-design.md 읽기
2. docs/claude-tools-guide.md 읽기
3. docs/architecture_allguzo.md 읽기
4. docs/requirements.md 읽기
5. docs/workflow_apiflow.md 읽기
```

### Step 3 — 각 문서에서 업데이트가 필요한 섹션 특정

각 문서를 읽은 후 "이 새 내용이 어느 섹션에 들어가야 하는가"를 결정.
관련 없는 문서는 건너뛰되, 건너뛰는 이유를 한 줄 설명.

### Step 4 — 문서별 업데이트 실행

- 기존 내용과 일관된 문체·형식 유지
- 수정일(최종 수정 날짜)이 있는 문서는 오늘 날짜로 갱신
- 새 섹션을 추가할 때는 기존 번호 체계(## 1. ## 2. ...)를 유지
- ASCII 다이어그램이 있는 문서는 다이어그램도 함께 업데이트

### Step 5 — 업데이트 완료 요약

아래 형식으로 결과 보고:

```
업데이트 완료: [추가된 것]

✓ design.md   — [어느 섹션에 무엇을 추가했는지]
✓ guide.md    — [어느 섹션에 무엇을 추가했는지]
✓ architecture_allguzo.md — [어느 섹션에 무엇을 추가했는지]
✓ requirements.md — [어느 섹션에 무엇을 추가했는지]
✓ workflow_apiflow.md — [어느 섹션에 무엇을 추가했는지]
- [건너뛴 문서] — 해당 없음 (이유)
```
