# M2 보안 탐지율 52% → 100% 디버깅 학습노트

작성일: 2026-06-06
작성자: Dev2 담당

---

## 한 줄 요약

정적 분석 에이전트 평가에서 탐지율이 52%였던 원인을 찾아 4가지를 고쳤더니 27/27 달성했다.
핵심은 "Bandit 미실행" 이었고, 나머지는 커스텀 스캐너와 매핑 오류였다.

---

## 1. 시작 상태와 목표

| 항목 | 이전 | 이후 |
|------|------|------|
| M2 탐지율 (P1) | 14/27 (52%) | **27/27 (100%)** |
| Pipeline 2 (P2) | ERROR (DB 오류) | **정상 동작** |

테스트 구조: `run_all.py`가 12개 케이스 디렉토리를 순회하며  
`vulnerable.py` → unified diff 변환 → `run_dev2()` → `check_hits()` 로 평가한다.

---

## 2. 버그 1: Pipeline 2 — developer_id 미전달 (NotNullViolationError)

### 원인

```python
# db.py - insert_aggregated_result 내부
scan_id = await insert_scan_execution(task_id, pr_id, execution_ms=0)
#                                                      ↑ developer_id 누락
```

`aggregate_graph.py` → `aggregate.py` → `db.py`로 `developer_id`가 전달됐지만
`insert_aggregated_result`가 `insert_scan_execution`을 호출할 때 빠뜨렸다.
`scan_executions.user_id`는 NOT NULL + FK 제약이라 바로 에러.

### 수정

```python
scan_id = await insert_scan_execution(task_id, pr_id, execution_ms=0, developer_id=developer_id)
```

### 교훈

함수 내부에서 다시 다른 함수를 호출할 때 파라미터를 통째로 전달하는 패턴에서  
하나라도 빠지면 FK 위반이 된다. 함수 시그니처에 `developer_id` 있다고 자동으로 전달되지 않는다.

---

## 3. 버그 2 (핵심): Bandit이 아예 실행 안 됨

### 증상

`command_injection_case`에서 `os.system(f"ping -c 1 {host}")` 코드가 있는데  
에이전트 출력에 bandit 결과가 전혀 없고 pylint 이슈만 나왔다.

```
detected: SA-C0114 (Missing module docstring)
detected: SA-C0116 (Missing function docstring)
← B605 없음
```

### 원인

`tool_router_agent.py`의 `build_tool_plan()` 로직:

```python
if ext == ".py":
    selected.update({"pylint", "radon"})   # 항상 선택
    if has_security_kw:                    # ← 이 조건을 통과해야만
        selected.update({"bandit", "semgrep"})  # bandit이 실행됨
```

`has_security_kw`는 `SECURITY_KEYWORDS` 목록에 있는 단어가  
diff 내용에 있을 때만 True가 된다.

```python
SECURITY_KEYWORDS = [
    "auth", "login", "password", "token", "sql", "subprocess",
    "eval(", "exec(", ...
    # os.system, secret, pathlib 없었음!
]
```

`command_injection_case`의 코드에는 `os.system`만 있고  
`SECURITY_KEYWORDS` 중 어느 것도 없어서 → `has_security_kw = False` → bandit skip.

`mixed_case_04` (`AWS_SECRET_KEY`, `BACKUP_DIR / filename`)도 같은 이유로 bandit skip.

### 수정

```python
SECURITY_KEYWORDS: list[str] = [
    # 기존 키워드...
    "os.system", "os.popen",  # shell/command injection
    "secret",                  # AWS_SECRET_KEY, JWT_SECRET 등
    "pathlib",                 # 경로 조작 (path traversal)
]
```

### 교훈

**라우팅 로직은 별도 테스트가 필요하다.**  
"bandit이 B605를 탐지하는가?" 보다 "bandit이 실행되기는 하는가?"가 먼저다.  
도구 체인에서 앞 단계가 막히면 뒷 단계는 아무 의미가 없다.

---

## 4. 버그 3: Bandit이 탐지 못하는 취약점 — 커스텀 스캐너 추가

Bandit에 없는 규칙 3가지를 `bandit_tool.py`에 직접 추가했다.

### (1) 경로 탐색 탐지 (_scan_path_traversal)

**Bandit에 경로 탐색 규칙 없음.** 직접 regex로 구현.

```python
_PATH_TRAVERSAL_PATTERNS = [
    # BACKUP_DIR / filename 형태 (pathlib division)
    re.compile(r'\b[A-Z][A-Z0-9_]+\s*/\s*([a-z_]\w*)'),
    # os.path.join(base, variable) 형태
    re.compile(r'os\.path\.join\s*\([^)]+,\s*([a-z_]\w*)\s*\)'),
]
```

탐지 대상 코드:
```python
BASE_DIR = pathlib.Path("/var/userfiles")
file_path = BASE_DIR / filename   # ← 이 패턴
```

### (2) 누락 인가 탐지 (_scan_missing_auth)

**정적 분석 도구로는 "해야 할 것이 없는" 패턴을 찾기 어렵다.**  
AST 파싱으로 "current_user를 가져왔지만 if에 쓰지 않고 변형 연산을 하면" 경고.

```python
def _scan_missing_auth(files):
    # 1. get_current_user() 호출 찾기 → 반환값 변수명 기억
    # 2. 그 변수가 if/compare 조건에 쓰였는지 확인
    # 3. 변형 연산(del, .remove, .pop)이 있으면 경고
```

취약 코드 패턴:
```python
def delete_user_account(self, session_token, target_user_id):
    current_user_id = self.get_current_user(session_token)  # 가져왔지만
    if target_user_id in self.users:  # current_user_id 비교 없음!
        del self.users[target_user_id]
```

### (3) 하드코딩 시크릿 패턴 개선 (_scan_hardcoded_secrets)

기존 패턴 문제: `\b(API_KEY|SECRET_KEY)` — 단어경계 때문에 앞에 prefix가 붙으면 안 잡힘.

```
JWT_SECRET = "..."    →  J-W-T-_-S: _ 뒤에 \b 없음 → 미탐지
AWS_SECRET_KEY = "..." → 동일한 이유로 미탐지
```

수정된 패턴:
```python
# [A-Z_]* 로 앞에 붙는 prefix(AWS_, JWT_)까지 허용
r'[A-Z_]*(?:SECRET|TOKEN|PASSWORD|CREDENTIAL|API_KEY|APIKEY)[A-Z0-9_]*\s*=\s*["\'].{8,}["\']'
```

---

## 5. 버그 4: RULE_KEYWORD_MAP 오매핑

평가 스크립트에서 expected rule_id → detected message 매핑 오류.

```python
# 수정 전 (잘못됨)
"SEC-003": ["B311", "path", "traversal"],  # B311은 난수 생성 규칙!
"SEC-004": ["B101", "assert", "auth"],     # SEC-004는 커맨드 인젝션인데 assert 키워드?

# 수정 후
"SEC-003": ["SEC-PT001", "path", "traversal"],  # 커스텀 스캐너 rule_id 사용
"SEC-004": ["B602", "B603", "B605", "command", "injection", "os.system"],
"AUTH-001": ["SEC-AUTH001", "authorization", "missing authorization"],
```

### 교훈

rule_id 매핑 테이블은 실제 도구가 출력하는 rule_id와 반드시 일치해야 한다.  
Bandit rule ID를 외우지 말고 `python -m bandit -r file.py -f json`으로 직접 확인.

---

## 6. 디버깅 순서 정리

이번 세션에서 효과적이었던 디버깅 방법:

```
1. 에이전트 전체 출력에서 detected issues 목록 확인
   → "Bandit 결과가 있는가?"

2. Bandit을 직접 실행해서 비교
   python -m bandit -r -f json file.py

3. 결과가 다르면 → 파이프라인의 어느 단계가 막혔는지 추적
   → tool_router_agent (bandit 선택됐는가?)
   → run_tools (실행됐는가?)
   → rule_id 매핑 (check_hits에서 keyword가 맞는가?)
```

---

## 7. 최종 MISS 원인 분류

| 케이스 | 기대 rule_id | MISS 원인 | 수정 방법 |
|--------|------------|-----------|-----------|
| command_injection_case | SEC-004 | SECURITY_KEYWORDS에 `os.system` 없음 → bandit skip | keyword 추가 |
| path_traversal_case | SEC-003 | Bandit에 경로탐색 규칙 없음 + keyword `pathlib` 없음 | 커스텀 스캐너 + keyword 추가 |
| mixed_case_04 | SEC-006, SEC-003, SEC-004 | SECURITY_KEYWORDS에 `secret`, `pathlib` 없음 → bandit skip | keyword 추가 |
| auth_missing_case | AUTH-001 | Bandit/semgrep 모두 미지원 (행위적 패턴) | AST 커스텀 스캐너 |
| mixed_case_02/03/05/06 | 위 조합 | 위 원인들의 조합 | 동일 |

---

## 복습 퀴즈

1. Q: `tool_router_agent`가 bandit을 실행하는 조건은?  
   A: (diff 내용에 `SECURITY_KEYWORDS` 중 하나 이상이 포함돼야 함. `.py` 파일이라고 무조건 실행되지 않는다)

2. Q: Bandit B311, B105, B605는 각각 어떤 취약점인가?  
   A: (B311=난수 생성, B105=하드코딩 패스워드, B605=os.system 셸 인젝션)

3. Q: `\b(SECRET_KEY)` 패턴이 `AWS_SECRET_KEY`를 못 잡는 이유는?  
   A: (`\b`는 단어경계. `_`는 `\w`에 속하므로 `_S` 사이에 단어경계가 없다)

4. Q: AUTH-001(누락 인가)을 정적 분석 도구가 탐지하기 어려운 이유는?  
   A: (있어야 할 코드가 없는 패턴이라서. 도구는 존재하는 코드를 검사하지, 없는 코드를 검사하지 않는다)
