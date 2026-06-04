# negative_self_query_method

## Purpose

Negative N+1 case (false-positive defense). Inside the loop the code calls
`self.query(...)`, but this is a **local in-memory string-matching helper**, not
a database session/ORM query. `PERF-002` must NOT be raised — a method merely
named `query` on a non-DB object is not a database call.

## Expected Issue

- `expected_issues`: `[]`
- Module: M3
- Source: Task-Link Custom

## Pattern

```python
def query(self, keyword):
    return [doc for doc in self.documents if keyword in doc]  # in-memory, NOT DB

for keyword in keywords:
    matches = self.query(keyword)  # local helper, not a DB query
```

## Files

- `app/`: target source code
- `tests/`: pytest tests
- `expected_issue.json`: expected M3 output for this case (empty)

## Notes

This dataset is for evaluation only and must not be used as production service code.
