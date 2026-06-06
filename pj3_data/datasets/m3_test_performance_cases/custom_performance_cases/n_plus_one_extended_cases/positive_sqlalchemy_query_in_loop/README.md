# positive_sqlalchemy_query_in_loop

## Purpose

Positive N+1 case. Validates `PERF-002` recall when a SQLAlchemy-style ORM
query (`session.query(...).filter(...).first()`) is executed inside a `for`-loop.

## Expected Issue

- Rule ID: `PERF-002`
- Severity: `Major`
- Module: M3
- Source: Task-Link Custom
- Target: `app/product_service.py::get_product_names`

## Pattern

```python
for product_id in product_ids:
    product = session.query(Product).filter(Product.id == product_id).first()  # N+1
```

## Files

- `app/`: target source code (`product_service.py`, `models.py`, `fake_session.py`)
- `tests/`: pytest tests
- `expected_issue.json`: expected M3 output for this case

## Notes

`fake_session.py` is a minimal in-memory stand-in for a SQLAlchemy Session so the
test runs without a real database. This dataset is for evaluation only and must
not be used as production service code.
