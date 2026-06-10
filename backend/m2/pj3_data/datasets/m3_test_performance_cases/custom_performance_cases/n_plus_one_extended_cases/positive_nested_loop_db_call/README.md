# positive_nested_loop_db_call

## Purpose

Positive N+1 case. Validates `PERF-002` recall when a repository lookup is
executed inside a **nested** `for`-loop.

## Expected Issue

- Rule ID: `PERF-002`
- Severity: `Major`
- Module: M3
- Source: Task-Link Custom
- Target: `app/report_service.py::build_team_member_report`

## Pattern

```python
for team in teams:
    for member_id in team["member_ids"]:
        member = member_repository.find_by_id(member_id)  # N+1 (nested)
```

## Files

- `app/`: target source code
- `tests/`: pytest tests
- `expected_issue.json`: expected M3 output for this case

## Notes

This dataset is for evaluation only and must not be used as production service code.
