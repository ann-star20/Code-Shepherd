# negative_bulk_fetch_before_loop

## Purpose

Negative N+1 case (false-positive defense). The related customers are fetched
**once in bulk before the loop** via `find_all_by_ids(...)`; inside the loop only
a `dict` lookup is performed. `PERF-002` must NOT be raised.

## Expected Issue

- `expected_issues`: `[]`
- Module: M3
- Source: Task-Link Custom

## Pattern

```python
customers_by_id = customer_repository.find_all_by_ids(customer_ids)  # bulk, before loop
for order in orders:
    customer = customers_by_id.get(order["customer_id"])  # dict lookup, NOT a query
```

## Files

- `app/`: target source code
- `tests/`: pytest tests
- `expected_issue.json`: expected M3 output for this case (empty)

## Notes

This dataset is for evaluation only and must not be used as production service code.
