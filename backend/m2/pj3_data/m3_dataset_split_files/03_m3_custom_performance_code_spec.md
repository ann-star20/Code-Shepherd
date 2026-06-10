# M3 Custom Performance Cases 코드 명세

## 목적

이 문서는 Claude Code가 `custom_performance_cases/` 하위에 생성해야 할 M3 custom code를 정의한다.

각 케이스는 다음 파일을 포함해야 한다.

```text
app/
tests/
README.md
expected_issue.json
```

---

# 1. low_coverage_case

## 목적

`pytest --cov` 실행 시 라인 커버리지가 80% 미만이 되도록 구성한다.

M3 expected issue:

```text
TEST-001
```

## 경로

```text
datasets/m3_test_performance_cases/custom_performance_cases/low_coverage_case/
```

## app/order_service.py

```python
def calculate_total(items):
    total = 0
    for item in items:
        total += item["price"] * item["quantity"]
    return total


def apply_discount(total, coupon_code):
    if coupon_code == "WELCOME":
        return total * 0.9
    if coupon_code == "VIP":
        return total * 0.8
    return total


def calculate_shipping(total, region):
    if region == "jeju":
        return 6000
    if total >= 50000:
        return 0
    return 3000


def create_order_summary(items, coupon_code, region):
    total = calculate_total(items)
    discounted = apply_discount(total, coupon_code)
    shipping = calculate_shipping(discounted, region)
    return {
        "total": total,
        "discounted": discounted,
        "shipping": shipping,
        "pay_amount": discounted + shipping,
    }
```

## tests/test_order_service.py

```python
from app.order_service import calculate_total


def test_calculate_total():
    items = [
        {"price": 10000, "quantity": 2},
        {"price": 5000, "quantity": 1},
    ]

    assert calculate_total(items) == 25000
```

## expected_issue.json

```json
{
  "case_id": "m3_custom_low_coverage_001",
  "module": "M3",
  "source": "Task-Link Custom",
  "expected_issues": [
    {
      "id": "TEST-001",
      "title": "Coverage below threshold",
      "severity": "Major",
      "target": "whole_project",
      "expected_metric": {
        "coverage_line_threshold": 0.8,
        "expected_below_threshold": true
      },
      "evidence": "Only calculate_total is tested while apply_discount, calculate_shipping, and create_order_summary remain untested."
    }
  ]
}
```

---

# 2. missing_test_function_case

## 목적

함수는 여러 개 있지만 일부 함수 본문이 테스트에서 실행되지 않도록 구성한다.

M3 expected issue:

```text
TEST-004
```

## 경로

```text
datasets/m3_test_performance_cases/custom_performance_cases/missing_test_function_case/
```

## app/user_metrics.py

```python
def average_score(scores):
    if not scores:
        return 0
    return sum(scores) / len(scores)


def normalize_score(score):
    if score < 0:
        return 0
    if score > 100:
        return 100
    return score


def grade_user(score):
    normalized = normalize_score(score)

    if normalized >= 90:
        return "A"
    if normalized >= 80:
        return "B"
    if normalized >= 70:
        return "C"
    return "D"
```

## tests/test_user_metrics.py

```python
from app.user_metrics import average_score


def test_average_score():
    assert average_score([80, 90, 100]) == 90
```

## expected_issue.json

```json
{
  "case_id": "m3_custom_missing_test_function_001",
  "module": "M3",
  "source": "Task-Link Custom",
  "expected_issues": [
    {
      "id": "TEST-004",
      "title": "Function missing test coverage",
      "severity": "Minor",
      "target_file": "app/user_metrics.py",
      "target_functions": ["normalize_score", "grade_user"],
      "evidence": "Function bodies are not executed by tests."
    }
  ]
}
```

---

# 3. n_plus_one_case

## 목적

반복문 내부에서 DB/repository 호출이 발생하는 N+1 쿼리 패턴을 구성한다.

M3 expected issue:

```text
PERF-002
```

## 경로

```text
datasets/m3_test_performance_cases/custom_performance_cases/n_plus_one_case/
```

## app/repositories.py

```python
class UserRepository:
    def __init__(self):
        self.users = {
            1: {"id": 1, "name": "Alice"},
            2: {"id": 2, "name": "Bob"},
            3: {"id": 3, "name": "Charlie"},
        }

    def find_by_id(self, user_id):
        return self.users.get(user_id)

    def find_all_by_ids(self, user_ids):
        return {
            user_id: self.users.get(user_id)
            for user_id in user_ids
        }
```

## app/post_service.py

```python
def get_posts_with_authors(posts, user_repository):
    result = []

    for post in posts:
        author = user_repository.find_by_id(post["user_id"])
        result.append({
            "post_id": post["id"],
            "title": post["title"],
            "author": author["name"] if author else None,
        })

    return result


def get_posts_with_authors_fixed(posts, user_repository):
    user_ids = {post["user_id"] for post in posts}
    users_by_id = user_repository.find_all_by_ids(user_ids)

    return [
        {
            "post_id": post["id"],
            "title": post["title"],
            "author": users_by_id.get(post["user_id"], {}).get("name"),
        }
        for post in posts
    ]
```

## tests/test_post_service.py

```python
from app.post_service import get_posts_with_authors
from app.repositories import UserRepository


def test_get_posts_with_authors():
    posts = [
        {"id": 1, "title": "hello", "user_id": 1},
        {"id": 2, "title": "world", "user_id": 2},
    ]

    result = get_posts_with_authors(posts, UserRepository())

    assert result[0]["author"] == "Alice"
    assert result[1]["author"] == "Bob"
```

## expected_issue.json

```json
{
  "case_id": "m3_custom_n_plus_one_001",
  "module": "M3",
  "source": "Task-Link Custom",
  "expected_issues": [
    {
      "id": "PERF-002",
      "title": "N+1 query pattern",
      "severity": "Major",
      "target_file": "app/post_service.py",
      "target_function": "get_posts_with_authors",
      "evidence": "user_repository.find_by_id is called inside a for-loop.",
      "recommendation": "Fetch related users in bulk before the loop."
    }
  ]
}
```

---

# 4. complexity_case

## 목적

중첩 루프 기반 시간복잡도 문제를 구성한다.

M3 expected issue:

```text
PERF-001
```

## 경로

```text
datasets/m3_test_performance_cases/custom_performance_cases/complexity_case/
```

## app/report_service.py

```python
def find_duplicate_pairs(users):
    duplicates = []

    for left in users:
        for right in users:
            if left["id"] == right["id"]:
                continue

            if left["email"] == right["email"]:
                duplicates.append((left["id"], right["id"]))

    return duplicates


def find_duplicate_pairs_fixed(users):
    seen = {}
    duplicates = []

    for user in users:
        email = user["email"]
        if email in seen:
            duplicates.append((seen[email], user["id"]))
        else:
            seen[email] = user["id"]

    return duplicates
```

## tests/test_report_service.py

```python
from app.report_service import find_duplicate_pairs


def test_find_duplicate_pairs():
    users = [
        {"id": 1, "email": "a@example.com"},
        {"id": 2, "email": "b@example.com"},
        {"id": 3, "email": "a@example.com"},
    ]

    result = find_duplicate_pairs(users)

    assert (1, 3) in result or (3, 1) in result
```

## expected_issue.json

```json
{
  "case_id": "m3_custom_complexity_001",
  "module": "M3",
  "source": "Task-Link Custom",
  "expected_issues": [
    {
      "id": "PERF-001",
      "title": "Time complexity issue",
      "severity": "Minor",
      "target_file": "app/report_service.py",
      "target_function": "find_duplicate_pairs",
      "evidence": "Nested loops over the same users collection create O(n^2) behavior.",
      "recommendation": "Use a dictionary or set to reduce lookup complexity."
    }
  ]
}
```

---

# 5. edge_case_missing_case

## 목적

정상 입력만 테스트하고 None, 0, 음수, 빈 리스트, 경계값 테스트가 빠진 케이스를 구성한다.

M3 expected issue:

```text
TEST-003
```

## 경로

```text
datasets/m3_test_performance_cases/custom_performance_cases/edge_case_missing_case/
```

## app/payment_service.py

```python
def calculate_payment_amount(price, quantity, discount_rate):
    subtotal = price * quantity
    discount = subtotal * discount_rate
    return subtotal - discount


def validate_payment_amount(amount):
    if amount <= 0:
        raise ValueError("Payment amount must be positive")
    return True
```

## tests/test_payment_service.py

```python
from app.payment_service import calculate_payment_amount


def test_calculate_payment_amount_normal_case():
    assert calculate_payment_amount(10000, 2, 0.1) == 18000
```

## expected_issue.json

```json
{
  "case_id": "m3_custom_edge_case_missing_001",
  "module": "M3",
  "source": "Task-Link Custom",
  "expected_issues": [
    {
      "id": "TEST-003",
      "title": "Missing edge case tests",
      "severity": "Minor",
      "target_file": "app/payment_service.py",
      "target_function": "calculate_payment_amount",
      "evidence": "Tests cover only a normal case and omit zero, negative, None, and boundary values.",
      "recommendation": "Add tests for price=0, quantity=0, negative values, None inputs, and discount boundaries."
    }
  ]
}
```

---

# 6. memory_leak_case

## 목적

전역 컨테이너가 요청마다 무제한 증가하는 메모리 누수 의심 패턴을 구성한다.

M3 expected issue:

```text
PERF-003
```

## 경로

```text
datasets/m3_test_performance_cases/custom_performance_cases/memory_leak_case/
```

## app/event_logger.py

```python
REQUEST_EVENTS = []


def log_request_event(user_id, path, payload):
    REQUEST_EVENTS.append({
        "user_id": user_id,
        "path": path,
        "payload": payload,
    })

    return len(REQUEST_EVENTS)


def get_event_count():
    return len(REQUEST_EVENTS)


def clear_events_for_test():
    REQUEST_EVENTS.clear()
```

## tests/test_event_logger.py

```python
from app.event_logger import clear_events_for_test, get_event_count, log_request_event


def test_log_request_event():
    clear_events_for_test()

    count = log_request_event(
        user_id=1,
        path="/api/orders",
        payload={"order_id": 10},
    )

    assert count == 1
    assert get_event_count() == 1
```

## expected_issue.json

```json
{
  "case_id": "m3_custom_memory_leak_001",
  "module": "M3",
  "source": "Task-Link Custom",
  "expected_issues": [
    {
      "id": "PERF-003",
      "title": "Memory leak pattern",
      "severity": "Minor",
      "target_file": "app/event_logger.py",
      "target_function": "log_request_event",
      "evidence": "Function appends request data to a global list without size limit or eviction policy.",
      "recommendation": "Use bounded queues, TTL cache, external logging, or explicit retention limits."
    }
  ]
}
```

---

# expected_outputs/expected_m3_issues.json 통합 예시

Claude Code는 각 케이스의 `expected_issue.json`를 모아 아래 파일도 생성해야 한다.

경로:

```text
datasets/expected_outputs/expected_m3_issues.json
```

예시 구조:

```json
{
  "module": "M3",
  "dataset": "m3_custom_performance_cases",
  "cases": [
    {
      "case_id": "m3_custom_low_coverage_001",
      "expected_issue_ids": ["TEST-001"]
    },
    {
      "case_id": "m3_custom_missing_test_function_001",
      "expected_issue_ids": ["TEST-004"]
    },
    {
      "case_id": "m3_custom_n_plus_one_001",
      "expected_issue_ids": ["PERF-002"]
    },
    {
      "case_id": "m3_custom_complexity_001",
      "expected_issue_ids": ["PERF-001"]
    },
    {
      "case_id": "m3_custom_edge_case_missing_001",
      "expected_issue_ids": ["TEST-003"]
    },
    {
      "case_id": "m3_custom_memory_leak_001",
      "expected_issue_ids": ["PERF-003"]
    }
  ]
}
```

---

# README.md 공통 템플릿

각 case의 `README.md`는 아래 형식을 따른다.

```md
# {case_name}

## Purpose

This case validates `{rule_id}` detection for the Task-Link M3 test/performance analysis agent.

## Expected Issue

- Rule ID: `{rule_id}`
- Severity: `{severity}`
- Module: M3
- Source: Task-Link Custom

## Files

- `app/`: target source code
- `tests/`: pytest tests
- `expected_issue.json`: expected M3 output for this case

## Notes

This dataset is for evaluation only and must not be used as production service code.
```
