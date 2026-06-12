# M4 개념 매핑 필드 추가 보고서

**작성일**: 2026-06-03  
**브랜치**: task-interpretation-agent  
**테스트**: 30/30 PASS (0.11s)

---

## 1. 배경 및 목적

M4 학습 커리큘럼 모듈이 이슈를 받아 학습자료를 생성하려면,
M2가 단순 이슈 설명 외에 **보안 개념 분류 + 실수 유형 + 코드 스니펫 + 프레임워크 정보**를 함께 넘겨야 함.

M2는 **구조화 데이터 생성까지만** 담당. 학습자료 생성은 M4가 담당.

---

## 2. 변경된 파일 (4개 수정 + 2개 신규)

| 파일 | 구분 | 변경 내용 |
|------|------|-----------|
| `dev2/schema.py` | 수정 | `LearningContext` 모델 추가, `Issue`에 M4 필드 7개 추가 |
| `dev2/nodes/concept_mapper.py` | **신규** | 룰 기반 개념 매핑 + snippet 추출 + learning_context 추론 |
| `dev2/nodes/llm_judge.py` | 수정 | `llm_judge_node` 끝에 매핑 호출 3줄 추가 |
| `dev2/nodes/store.py` | 수정 | `_ISSUE_FIELDS`에 M4 필드 + 기존 누락 필드 추가 |
| `dev2/tests/test_concept_mapper.py` | **신규** | 테스트 30개 |
| `docs/plans/prd_m2.md` | 수정 | 출력 계약 예시 업데이트 |

---

## 3. schema.py 변경

### 추가된 모델

```python
class LearningContext(BaseModel):
    framework: str = "none"       # "django" | "fastapi" | "flask" | "none"
    language: str = "python"      # "python" | "javascript" | ...
    domain_context: str = "ecommerce"  # MVP 기본값
```

### Issue에 추가된 필드 (모두 optional, 기본값 있음)

```python
concept: str = ""                    # "SQL Injection" | "XSS" | "CSRF" | "AUTH_VULNERABILITY"
mistake_type: str = ""               # "raw_query" | "mark_safe_misuse" | ...
concept_id: str = ""                 # "sql_injection" | "xss" | ...
mistake_type_concept_id: str = ""    # "sql_injection.raw_query" | ...
confidence_score: float = 0.0        # 0.0 ~ 1.0
code_snippet: str = ""               # 문제 코드 조각
learning_context: LearningContext = LearningContext()
```

**기존 필드 전혀 건드리지 않음.** 하위 호환성 유지.

---

## 4. concept_mapper.py 핵심 로직

### 매핑 우선순위

```
1. rule_id 직접 매핑   → confidence 높음 (0.85~0.95)
2. message 패턴 매핑   → confidence 중간 (0.60~0.82)
3. 미매핑               → concept="" confidence=0.0 (lint 등)
```

### 지원 rule_id

| rule_id | concept | mistake_type | confidence |
|---------|---------|--------------|------------|
| B608 | SQL Injection | raw_query | 0.92 |
| SEC-B608 | SQL Injection | raw_query | 0.92 |
| B703 | XSS | mark_safe_misuse | 0.90 |
| B308 | XSS | mark_safe_misuse | 0.88 |
| B506 | CSRF | csrf_exempt_misuse | 0.88 |
| B105 | AUTH_VULNERABILITY | hardcoded_credential | 0.95 |
| B106 | AUTH_VULNERABILITY | hardcoded_credential | 0.95 |

### confidence 기준

```
>= 0.8 → mistake_type 명확 매핑 (mistake_type_concept_id 채워짐)
<  0.8 → mistake_type = "general", mistake_type_concept_id = "{concept_id}.general"
```

### code_snippet 추출

- unified diff에서 target_file + target_line 찾아 `+` 라인 추출
- 못 찾으면 `"snippet_unavailable"` (빈 문자열 아님)

### learning_context 추론

- 파일 확장자 → language (`.py` → `python`, `.js/.jsx` → `javascript` 등)
- tech_stack 또는 파일 경로 → framework (`django`, `fastapi`, `flask`, `none`)
- domain_context → `"ecommerce"` (MVP 기본값)

---

## 5. llm_judge.py 변경 (3줄 추가)

```python
# severity 재판단 완료 후 M4 개념 매핑 적용
pr_diff: str = state.get("pr_diff", "")
judged = [
    enrich_with_concept_mapping(j, pr_diff, tech_stack)
    for j in judged
]
```

파이프라인 위치: `llm_judge` → **concept mapping** → `store`

---

## 6. store.py 변경 (_ISSUE_FIELDS)

### 변경 전
```python
_ISSUE_FIELDS = frozenset({
    "severity", "line", "file", "message", "rule_id", "suggestion", "similar_issues",
})
```

### 변경 후
```python
_ISSUE_FIELDS = frozenset({
    # 기존 필드 (issue_type, resolution_example, status 누락 버그도 수정)
    "severity", "issue_type", "line", "file", "message", "rule_id",
    "suggestion", "resolution_example", "status", "similar_issues",
    # M4 매핑 필드
    "concept", "mistake_type", "concept_id", "mistake_type_concept_id",
    "confidence_score", "code_snippet", "learning_context",
})
```

> **부가 수정**: `issue_type`, `resolution_example`, `status` 필드가 기존에도 `Issue` 모델에 있었지만 `_ISSUE_FIELDS` 누락으로 AgentOutput 출력에서 걸러지던 버그를 같이 수정.

---

## 7. 최종 출력 예시

```json
{
  "agent": "security_scan",
  "task_id": "uuid-001",
  "issues": [
    {
      "severity": "Critical",
      "issue_type": "Vulnerability",
      "line": 42,
      "file": "src/auth.py",
      "message": "SQL 인젝션 가능성",
      "rule_id": "B608",
      "suggestion": "파라미터화된 쿼리 사용",
      "resolution_example": "",
      "similar_issues": [],

      "concept": "SQL Injection",
      "mistake_type": "raw_query",
      "concept_id": "sql_injection",
      "mistake_type_concept_id": "sql_injection.raw_query",
      "confidence_score": 0.92,
      "code_snippet": "query = \"SELECT * FROM users WHERE name = '\" + username + \"'\"",
      "learning_context": {
        "framework": "django",
        "language": "python",
        "domain_context": "ecommerce"
      }
    }
  ],
  "summary": {"critical": 1, "major": 0, "minor": 0},
  "execution_ms": 1200
}
```

---

## 8. 테스트 결과

```
30 passed in 0.11s
```

| 테스트 클래스 | 테스트 수 | 내용 |
|---|---|---|
| `TestLookupConcept` | 7 | rule_id / message 패턴 매핑 |
| `TestConfidenceThreshold` | 2 | confidence 0.8 기준 분기 |
| `TestExtractSnippet` | 4 | snippet 추출 + unavailable fallback |
| `TestInferLearningContext` | 6 | 언어/프레임워크 추론 |
| `TestEnrichWithConceptMapping` | 8 | 통합 + 기존 필드 보존 |
| `TestAgentOutputPydantic` | 3 | Pydantic 검증 통과 |

---

## 9. M4 연동 시 주의사항

- `concept == ""` → 매핑 미지원 이슈 (lint 등). M4에서 무시 처리 권장.
- `learning_context.domain_context` = `"ecommerce"` 고정 (MVP). Week 5에 실제 프로젝트 도메인으로 교체 가능.
- M4가 concept 기반 학습자료를 만들 때 `mistake_type_concept_id`를 그래프 DB 노드 ID로 사용.
