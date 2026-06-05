# 팀 공통 개발 가이드라인

**대상**: 전 모듈 담당자 (Module 0 ~ Module 5, FE)  
**목적**: 협업 진입점 — 세부 규칙은 아래 참조 문서로 연결됩니다.

> **세부 Agent/Validation/Harness/Pydantic 규칙** → [`docs/GLOBAL_AGENT_RULE.md`](GLOBAL_AGENT_RULE.md)  
> **LangGraph State 스키마** → [`docs/AGENT_STATE_SCHEMA.md`](AGENT_STATE_SCHEMA.md)  
> **모듈 간 Output Contract** → [`docs/MODULE_CONTRACT.md`](MODULE_CONTRACT.md)  
> **브랜치 구조 상세** → [`docs/branch-strategy.md`](branch-strategy.md)

---

## 1. 브랜치 전략 (요약)

| 브랜치 | 역할 |
|--------|------|
| `main` | 배포 브랜치 — 직접 push 금지 |
| `dev` | 통합 개발 브랜치 — feature/* PR 대상 |
| `feature/*` | 모듈별 개발 브랜치 |

```text
feature/{module}  →  PR  →  dev  →  (Week 5 통합)  →  main
```

---

## 2. 개발 프로세스

### PR 요건

```text
□ 단위 테스트 통과 (Mock 기반, 실 DB/LLM 없이)
□ Output Contract 변경 시 → docs/MODULE_CONTRACT.md 업데이트 + 영향 모듈 공지
□ src/common/state.py 변경 시 → PR description 명시 + 전 모듈 알림
□ 최소 1명 코드 리뷰 승인
```

### 절대 금지

```text
✗ main 직접 push
✗ 다른 모듈 담당 파일 임의 수정
✗ --force push / --no-verify
✗ 자동 머지 코드 (PR 최종 결정은 항상 사람이 한다)
```

---

## 3. 공통 개발 원칙

- 모듈 간 직접 import 금지 — Output Contract JSON으로만 통신
- Orchestrator(Module 1)가 호출 가능한 형태 유지
- 모든 함수 시그니처에 타입 힌트 필수 (TypedDict 또는 Pydantic)
- SQL은 파라미터 바인딩만 — f-string SQL 조합 금지

### 공통 반환 필드 (필수 포함)

```python
{
    "trace_id": "...",         # LangSmith trace와 연동
    "status": "success | failed | pending | hitl_required",
    "error_message": None      # 성공 시 None, 실패 시 문자열
}
```

> Agent 출력 전체 Contract → [`docs/GLOBAL_AGENT_RULE.md §4`](GLOBAL_AGENT_RULE.md)

---

## 4. Agent / Workflow / LLM Node / Tool 구분

> **이미 정의됨** → [`docs/GLOBAL_AGENT_RULE.md §1`](GLOBAL_AGENT_RULE.md)

---

## 5. LangSmith + Harness

> **이미 정의됨** → [`docs/GLOBAL_AGENT_RULE.md §7~8`](GLOBAL_AGENT_RULE.md)  
> **빠른 시작** → [`docs/harness-guide.md`](harness-guide.md)

### LangSmith 프로젝트 네이밍 (요약)

```bash
# 개발 중: 반드시 본인 GitHub ID 포함
LANGCHAIN_PROJECT=module{N}-{yourGitHubId}

# 통합 주간 (Week 5)
LANGCHAIN_PROJECT=onboarding-platform-integrated
```

---

## 6. Mock / 실제 LLM 전환

```bash
USE_MOCK_LLM=true    # 개발 중 (실제 API 호출 없음)
USE_MOCK_LLM=false   # 통합 테스트 / 데모
```

코드 변경 없이 환경변수만으로 전환한다.
