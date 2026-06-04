# positive_repository_find_by_id

## Purpose

Positive N+1 case. Validates `PERF-002` recall when a repository lookup
(`customer_repository.find_by_id(...)`) is executed inside a `for`-loop.

## Expected Issue

- Rule ID: `PERF-002`
- Severity: `Major`
- Module: M3
- Source: Task-Link Custom
- Target: `app/order_service.py::get_orders_with_customers`

## Pattern

```python
for order in orders:
    customer = customer_repository.find_by_id(order["customer_id"])  # N+1
```

## Files

- `app/`: target source code
- `tests/`: pytest tests
- `expected_issue.json`: expected M3 output for this case

## Notes

This dataset is for evaluation only and must not be used as production service code.
