# negative_loop_without_db_call

## Purpose

Negative N+1 case (false-positive defense). The loops perform only string and
numeric processing — there is **no database/repository call** anywhere.
`PERF-002` must NOT be raised.

## Expected Issue

- `expected_issues`: `[]`
- Module: M3
- Source: Task-Link Custom

## Pattern

```python
for sentence in sentences:
    words = sentence.split()
    for word in words:
        total_length += len(word)   # pure computation, no query
```

## Files

- `app/`: target source code
- `tests/`: pytest tests
- `expected_issue.json`: expected M3 output for this case (empty)

## Notes

This dataset is for evaluation only and must not be used as production service code.
