# negative_local_dict_get

## Purpose

Negative N+1 case (false-positive defense). Inside the loop the code calls
`users_by_id.get(...)`, which is a plain **dict lookup**, not a database query.
`PERF-002` must NOT be raised — `.get()` on an in-memory dict is not a DB call.

## Expected Issue

- `expected_issues`: `[]`
- Module: M3
- Source: Task-Link Custom

## Pattern

```python
for post in posts:
    author = users_by_id.get(post["user_id"])  # dict.get, NOT a query
```

## Files

- `app/`: target source code
- `tests/`: pytest tests
- `expected_issue.json`: expected M3 output for this case (empty)

## Notes

This dataset is for evaluation only and must not be used as production service code.
