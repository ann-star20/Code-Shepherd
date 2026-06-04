# positive_db_execute_in_loop

## Purpose

Positive N+1 case. Validates `PERF-002` recall when a raw `db.execute(...)`
query is executed inside a `for`-loop.

## Expected Issue

- Rule ID: `PERF-002`
- Severity: `Major`
- Module: M3
- Source: Task-Link Custom
- Target: `app/invoice_service.py::load_invoice_totals`

## Pattern

```python
for invoice_id in invoice_ids:
    row = db.execute("SELECT total FROM invoices WHERE id = ?", (invoice_id,))  # N+1
```

## Files

- `app/`: target source code
- `tests/`: pytest tests
- `expected_issue.json`: expected M3 output for this case

## Notes

This dataset is for evaluation only and must not be used as production service code.
