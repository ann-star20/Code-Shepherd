# M2 Custom Security Cases 코드 명세 v2

## 목적

이 문서는 Claude Code가 `m2_custom_security_cases/` 하위에 생성해야 할 커스텀 보안 케이스 코드를 정의한다.

v2 변경점:

```text
expected_issue.json을 Dev2 Output Contract에 맞춰 확장한다.
```

각 케이스는 다음 파일을 포함해야 한다.

```text
vulnerable.py
fixed.py
README.md
expected_issue.json
```

각 `expected_issue.json`의 issue 객체는 반드시 아래 필드를 포함한다.

```text
severity
issue_type
line
file
message
rule_id
suggestion
resolution_example
similar_issues
```

---

# 1. sqli_case

## 목적

SQL Injection 취약점 탐지 검증.

## 경로

```text
datasets/m2_custom_security_cases/sqli_case/
```

## vulnerable.py

```python
class FakeDatabase:
    def execute(self, query: str):
        return {"query": query, "rows": []}


def search_users(keyword: str, db: FakeDatabase):
    query = f"SELECT id, name, email FROM users WHERE name = '{keyword}'"
    return db.execute(query)
```

## fixed.py

```python
class FakeDatabase:
    def execute(self, query: str, params=None):
        return {"query": query, "params": params or {}, "rows": []}


def search_users(keyword: str, db: FakeDatabase):
    query = "SELECT id, name, email FROM users WHERE name = :keyword"
    return db.execute(query, {"keyword": keyword})
```

## expected_issue.json

```json
{
  "case_id": "m2_custom_sqli_001",
  "module": "M2",
  "source": "Task-Link Custom",
  "agent": "security_scan",
  "expected_issues": [
    {
      "severity": "Critical",
      "issue_type": "Vulnerability",
      "line": 7,
      "file": "vulnerable.py",
      "message": "SQL Injection 가능성: 사용자 입력이 SQL 쿼리에 직접 삽입됩니다.",
      "rule_id": "SEC-001",
      "suggestion": "파라미터화된 쿼리를 사용하세요.",
      "resolution_example": "f-string SQL 조합 대신 db.execute(query, {\"keyword\": keyword}) 형태를 사용하세요.",
      "similar_issues": []
    }
  ]
}
```

---

# 2. path_traversal_case

## 목적

Path Traversal 취약점 탐지 검증.

## 경로

```text
datasets/m2_custom_security_cases/path_traversal_case/
```

## vulnerable.py

```python
from pathlib import Path


BASE_DIR = Path("/app/uploads")


def read_user_file(filename: str) -> str:
    target_path = BASE_DIR / filename
    return target_path.read_text(encoding="utf-8")
```

## fixed.py

```python
from pathlib import Path


BASE_DIR = Path("/app/uploads").resolve()


def read_user_file(filename: str) -> str:
    target_path = (BASE_DIR / filename).resolve()

    if not str(target_path).startswith(str(BASE_DIR)):
        raise ValueError("Invalid file path")

    return target_path.read_text(encoding="utf-8")
```

## expected_issue.json

```json
{
  "case_id": "m2_custom_path_traversal_001",
  "module": "M2",
  "source": "Task-Link Custom",
  "agent": "security_scan",
  "expected_issues": [
    {
      "severity": "Critical",
      "issue_type": "Vulnerability",
      "line": 8,
      "file": "vulnerable.py",
      "message": "Path Traversal 가능성: 사용자 입력 파일명이 경로 검증 없이 파일 접근에 사용됩니다.",
      "rule_id": "SEC-003",
      "suggestion": "입력 경로를 resolve한 뒤 허용된 base directory 내부인지 검증하세요.",
      "resolution_example": "target_path = (BASE_DIR / filename).resolve(); base 경로 밖이면 예외를 발생시키세요.",
      "similar_issues": []
    }
  ]
}
```

---

# 3. command_injection_case

## 목적

Command Injection 취약점 탐지 검증.

## 경로

```text
datasets/m2_custom_security_cases/command_injection_case/
```

## vulnerable.py

```python
import os


def ping_host(host: str) -> int:
    command = f"ping -c 1 {host}"
    return os.system(command)
```

## fixed.py

```python
import subprocess


def ping_host(host: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["ping", "-c", "1", host],
        check=False,
        capture_output=True,
        text=True,
    )
```

## expected_issue.json

```json
{
  "case_id": "m2_custom_command_injection_001",
  "module": "M2",
  "source": "Task-Link Custom",
  "agent": "security_scan",
  "expected_issues": [
    {
      "severity": "Critical",
      "issue_type": "Vulnerability",
      "line": 5,
      "file": "vulnerable.py",
      "message": "Command Injection 가능성: 사용자 입력이 shell command 문자열에 직접 삽입됩니다.",
      "rule_id": "SEC-004",
      "suggestion": "문자열 명령어 대신 subprocess 인자 배열을 사용하세요.",
      "resolution_example": "subprocess.run([\"ping\", \"-c\", \"1\", host], shell=False)를 사용하세요.",
      "similar_issues": []
    }
  ]
}
```

---

# 4. auth_missing_case

## 목적

권한 검증 누락 탐지 검증.

## 경로

```text
datasets/m2_custom_security_cases/auth_missing_case/
```

## vulnerable.py

```python
class User:
    def __init__(self, user_id: int, is_admin: bool = False):
        self.user_id = user_id
        self.is_admin = is_admin


class UserRepository:
    def delete_user(self, user_id: int):
        return {"deleted_user_id": user_id}


def delete_user_account(current_user: User, target_user_id: int, repository: UserRepository):
    return repository.delete_user(target_user_id)
```

## fixed.py

```python
class User:
    def __init__(self, user_id: int, is_admin: bool = False):
        self.user_id = user_id
        self.is_admin = is_admin


class UserRepository:
    def delete_user(self, user_id: int):
        return {"deleted_user_id": user_id}


def delete_user_account(current_user: User, target_user_id: int, repository: UserRepository):
    if not current_user.is_admin and current_user.user_id != target_user_id:
        raise PermissionError("Not allowed to delete this account")

    return repository.delete_user(target_user_id)
```

## expected_issue.json

```json
{
  "case_id": "m2_custom_auth_missing_001",
  "module": "M2",
  "source": "Task-Link Custom",
  "agent": "security_scan",
  "expected_issues": [
    {
      "severity": "Major",
      "issue_type": "Vulnerability",
      "line": 13,
      "file": "vulnerable.py",
      "message": "권한 검증 누락: 사용자 삭제 함수가 current_user 권한을 확인하지 않습니다.",
      "rule_id": "AUTH-001",
      "suggestion": "관리자 여부 또는 리소스 소유자 여부를 확인한 뒤 삭제를 수행하세요.",
      "resolution_example": "if not current_user.is_admin and current_user.user_id != target_user_id: raise PermissionError(...)",
      "similar_issues": []
    }
  ]
}
```

---

# 5. insecure_password_hash_case

## 목적

약한 해시 알고리즘 탐지 검증.

## 경로

```text
datasets/m2_custom_security_cases/insecure_password_hash_case/
```

## vulnerable.py

```python
import hashlib


def hash_password(password: str) -> str:
    return hashlib.md5(password.encode("utf-8")).hexdigest()
```

## fixed.py

```python
import hashlib
import os


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        100_000,
    )
    return f"{salt.hex()}:{digest.hex()}"
```

## expected_issue.json

```json
{
  "case_id": "m2_custom_weak_hash_001",
  "module": "M2",
  "source": "Task-Link Custom",
  "agent": "security_scan",
  "expected_issues": [
    {
      "severity": "Major",
      "issue_type": "Vulnerability",
      "line": 5,
      "file": "vulnerable.py",
      "message": "약한 비밀번호 해싱: 비밀번호 저장에 MD5가 사용됩니다.",
      "rule_id": "SEC-005",
      "suggestion": "bcrypt, Argon2, PBKDF2처럼 salt와 반복 횟수를 지원하는 비밀번호 해싱 방식을 사용하세요.",
      "resolution_example": "hashlib.pbkdf2_hmac 또는 passlib/bcrypt/argon2를 사용하고 salt를 함께 저장하세요.",
      "similar_issues": []
    }
  ]
}
```

---

# 6. hardcoded_secret_case

## 목적

하드코딩된 비밀값 탐지 검증.

## 경로

```text
datasets/m2_custom_security_cases/hardcoded_secret_case/
```

## vulnerable.py

```python
DATABASE_URL = "postgresql://admin:super-secret-password@localhost:5432/tasklink"
JWT_SECRET = "hardcoded-jwt-secret-key"
OPENAI_API_KEY = "sk-test-hardcoded-example"


def get_database_url() -> str:
    return DATABASE_URL


def create_token_payload(user_id: int) -> dict:
    return {
        "user_id": user_id,
        "signed_with": JWT_SECRET,
    }
```

## fixed.py

```python
import os


def get_database_url() -> str:
    value = os.getenv("DATABASE_URL")
    if not value:
        raise RuntimeError("DATABASE_URL is not configured")
    return value


def get_jwt_secret() -> str:
    value = os.getenv("JWT_SECRET")
    if not value:
        raise RuntimeError("JWT_SECRET is not configured")
    return value


def create_token_payload(user_id: int) -> dict:
    return {
        "user_id": user_id,
        "signed_with": get_jwt_secret(),
    }
```

## expected_issue.json

```json
{
  "case_id": "m2_custom_hardcoded_secret_001",
  "module": "M2",
  "source": "Task-Link Custom",
  "agent": "security_scan",
  "expected_issues": [
    {
      "severity": "Critical",
      "issue_type": "Vulnerability",
      "line": 1,
      "file": "vulnerable.py",
      "message": "하드코딩된 비밀값: DB 비밀번호, JWT secret, API key 형태의 값이 코드에 직접 포함되어 있습니다.",
      "rule_id": "SEC-006",
      "suggestion": "비밀값은 환경변수 또는 Secret Manager로 분리하세요.",
      "resolution_example": "os.getenv(\"DATABASE_URL\")와 os.getenv(\"JWT_SECRET\")로 런타임에 주입받으세요.",
      "similar_issues": []
    }
  ]
}
```

---

# expected_outputs/expected_m2_issues.json 통합 예시

Claude Code는 각 케이스의 `expected_issue.json`를 모아 아래 파일도 생성해야 한다.

경로:

```text
datasets/expected_outputs/expected_m2_issues.json
```

예시 구조:

```json
{
  "module": "M2",
  "dataset": "m2_owasp_benchmark_python_selected",
  "cases": [
    {
      "case_id": "m2_custom_sqli_001",
      "source": "Task-Link Custom",
      "agent": "security_scan",
      "expected_issues": [
        {
          "severity": "Critical",
          "issue_type": "Vulnerability",
          "line": 7,
          "file": "m2_custom_security_cases/sqli_case/vulnerable.py",
          "message": "SQL Injection 가능성: 사용자 입력이 SQL 쿼리에 직접 삽입됩니다.",
          "rule_id": "SEC-001",
          "suggestion": "파라미터화된 쿼리를 사용하세요.",
          "resolution_example": "f-string SQL 조합 대신 db.execute(query, {\"keyword\": keyword}) 형태를 사용하세요.",
          "similar_issues": []
        }
      ]
    },
    {
      "case_id": "m2_custom_path_traversal_001",
      "source": "Task-Link Custom",
      "agent": "security_scan",
      "expected_issues": [
        {
          "severity": "Critical",
          "issue_type": "Vulnerability",
          "line": 8,
          "file": "m2_custom_security_cases/path_traversal_case/vulnerable.py",
          "message": "Path Traversal 가능성: 사용자 입력 파일명이 경로 검증 없이 파일 접근에 사용됩니다.",
          "rule_id": "SEC-003",
          "suggestion": "입력 경로를 resolve한 뒤 허용된 base directory 내부인지 검증하세요.",
          "resolution_example": "target_path = (BASE_DIR / filename).resolve(); base 경로 밖이면 예외를 발생시키세요.",
          "similar_issues": []
        }
      ]
    }
  ]
}
```

나머지 4개 케이스도 같은 형식으로 추가한다.

---

# README.md 공통 템플릿

각 case의 `README.md`는 아래 형식을 따른다.

```md
# {case_name}

## Purpose

This case validates `{rule_id}` detection for the Task-Link M2 security/static analysis agent.

## Expected Issue

- Rule ID: `{rule_id}`
- Severity: `{severity}`
- Issue Type: Vulnerability
- Module: M2
- Agent: security_scan
- Source: Task-Link Custom

## Files

- `vulnerable.py`: intentionally vulnerable code
- `fixed.py`: safe reference implementation
- `expected_issue.json`: expected M2 output for this case

## Output Contract Fields

Each expected issue must include:

- `severity`
- `issue_type`
- `line`
- `file`
- `message`
- `rule_id`
- `suggestion`
- `resolution_example`
- `similar_issues`

## Notes

This dataset is for evaluation only and must not be used as production service code.
```
