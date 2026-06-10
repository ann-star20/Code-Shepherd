"""
severity_judge.py — LLM severity 재판단 프롬프트 빌더

이 모듈은 프롬프트 문자열만 생성한다. LLM을 직접 호출하지 않는다.
→ 테스트 용이성: LLM/API 없이 순수 Python으로 테스트 가능

프롬프트 구성 요소 4가지:
    ① Few-shot Prompting: 판단 기준 calibration (3가지 예시)
    ② Chain-of-Thought: 단계별 분석 강제 (패턴→과거비교→등급→조언)
    ③ RAG Context 주입: pgVector로 검색된 similar_cases를 컨텍스트로 주입
    ④ Structured Output: {"severity", "suggestion", "rationale"} JSON 형식 강제
        → CLAUDE.md §12: LLM 응답은 반드시 파싱/검증 후 사용

실제 LLM 호출은 llm_judge_node()가 담당한다. (dev2/nodes/llm_judge.py)
"""

# ① Few-shot Prompting: 3가지 등급 예시 (Critical/Major/Minor 골고루)
# 이 예시들이 LLM의 severity 기준을 우리 팀 기준으로 calibration한다
FEW_SHOT_EXAMPLES = """
[판단 예시 — Few-shot Calibration]
예시 1) SQL 파라미터 미처리 → Critical / Vulnerability
        이유: 입력값이 직접 SQL 쿼리에 삽입됨. 즉시 수정, 배포 차단.
        resolution_example: "f-string SQL 조합 금지. asyncpg :param 또는 SQLAlchemy bindparams() 사용"

예시 2) 순환복잡도 15 감지 → Major / Code Smell
        이유: 함수 분기 15개 이상 → 테스트 불가, 리팩토링 필수.
        resolution_example: "함수를 5분기 이하 단위로 분리하고 guard clause 패턴 적용"

예시 3) 변수명 snake_case 위반 → Minor / Code Smell
        이유: 코드 스멜. 기능 영향 없음. 다음 PR에서 수정 권장.
        resolution_example: "myVar → my_var (PEP8 snake_case 적용)"
"""

# ── 도메인별 규칙 가이드라인 ──────────────────────────────────────────────────
_FRONTEND_RULES = """
[Frontend 도메인 규칙 — JS/TS/React]
- eval() 사용 → Vulnerability / Critical  (resolution: "eval 제거, JSON.parse() 또는 함수 리팩토링")
- dangerouslySetInnerHTML → Vulnerability / Critical  (resolution: "DOMPurify.sanitize() 적용 후 사용")
- var 변수 선언 → Code Smell / Minor  (resolution: "var → const/let 으로 교체")
- 컴포넌트 복잡도 과다 / 불필요한 useEffect 의존성 → Code Smell / Major
"""

_BACKEND_RULES = """
[Backend 도메인 규칙 — Python/FastAPI/DB]
- SQL f-string 조합 → Vulnerability / Critical  (resolution: "f-string 제거, 파라미터 바인딩(:param) 사용")
- 하드코딩된 API 키/비밀번호 → Vulnerability / Critical  (resolution: "os.getenv() + .env 파일로 외부화")
- == None 비교 → Code Smell / Minor  (resolution: "== None 말고 is None 써라")
- N+1 쿼리 패턴 → Bug / Major  (resolution: "joinedload() 또는 selectinload()로 eager loading 적용")
- with 구문 없는 파일/DB 연결 → Bug / Major  (resolution: "async with ... 또는 contextmanager로 래핑")
"""


def build_severity_prompt(
    message: str,
    current_severity: str,
    developer_level: str,
    similar_cases: list[dict],
    tech_stack: list[str] | None = None,
    file_name: str = "",
) -> str:
    """
    LLM에 전달할 severity 재판단 프롬프트를 조립한다.

    ③ RAG context: similar_cases는 vector_search_node가 pgVector로 검색한 유사 이슈다.
    → LLM이 과거 팀 이력을 참고해 더 정확한 판단을 내릴 수 있다.
    → CLAUDE.md §12: 검색 결과 0건 → "유사 사례 없음" 표시 (예외 던지지 않음)

    Args:
        message: CLI 도구가 탐지한 이슈 메시지
        current_severity: CLI 도구가 매긴 severity ("Critical"|"Major"|"Minor")
        developer_level: 개발자 스킬 레벨 ("junior"|"mid"|"senior")
        similar_cases: pgVector로 검색된 유사 과거 이슈 목록
                       각 항목: {"pr_id": str, "similarity": float, "message": str}
        tech_stack: 개발자 기술 스택 (예: ["python", "fastapi"] 또는 ["react", "typescript"])
        file_name: 분석 대상 파일명 (확장자로 도메인 판별에 사용)

    Returns:
        LLM에 전달할 완성된 프롬프트 문자열
    """
    tech_stack = tech_stack or []

    # ── 도메인 규칙 선택 (파일 확장자 + tech_stack 기반) ─────────────────────
    ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    fe_exts = {"js", "jsx", "ts", "tsx", "vue", "svelte"}
    fe_stacks = {"javascript", "typescript", "react", "vue", "svelte", "nextjs"}
    is_frontend = ext in fe_exts or bool(fe_stacks & {s.lower() for s in tech_stack})
    domain_rules = _FRONTEND_RULES if is_frontend else _BACKEND_RULES

    # ③ RAG Context — CLAUDE.md §12: pgVector 0결과 처리
    if similar_cases:
        cases_text = "\n".join(
            f"  - PR #{c['pr_id']} (유사도 {c.get('similarity', 0):.2f}): {c.get('message', '')}"
            for c in similar_cases
        )
    else:
        cases_text = "  유사 사례 없음 (처음 발견된 패턴)"

    # ④ Structured Output: JSON 응답 형식 강제
    # {{ }}은 f-string에서 리터럴 중괄호 ({})를 출력하기 위한 이스케이프
    return f"""{FEW_SHOT_EXAMPLES}
{domain_rules}

[과거 유사 사례 — RAG Context (pgVector 코사인 유사도 검색)]
{cases_text}

[분석 단계 — Chain-of-Thought]
1단계) 현재 이슈의 패턴이 무엇인가? (SQL 인젝션? 복잡도? 코드 스멜?)
2단계) 과거 유사 사례와 비교하면 어떤 차이가 있나?
3단계) 최종 severity(Critical|Major|Minor)와 issue_type(Bug|Vulnerability|Code Smell)을 결정하라
4단계) {developer_level} 수준의 개발자에게 맞춤 개선 방법을 제시하라
5단계) "A 말고 B 써라" 형태의 한 줄 resolution_example을 작성하라

[현재 이슈]
파일: {file_name or "알 수 없음"}
메시지: {message}
도구 판단 severity: {current_severity}
개발자 수준: {developer_level}

위 단계를 거쳐 판단한 후, 반드시 아래 JSON 형식으로만 응답하라:
{{"severity": "Critical|Major|Minor", "issue_type": "Bug|Vulnerability|Code Smell", "suggestion": "구체적인 수정 방법 (코드 예시 포함)", "resolution_example": "A 말고 B 써라 형태의 한 줄 교정 코드", "rationale": "판단 근거 한 줄"}}"""
