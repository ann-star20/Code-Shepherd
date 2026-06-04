from app.models import Product


class _Query:
    def __init__(self, store):
        self._store = store
        self._wanted_id = None

    def filter(self, comparison):
        self._wanted_id = comparison.value
        return self

    def first(self):
        return self._store.get(self._wanted_id)


class FakeSession:
    """Minimal stand-in for a SQLAlchemy Session for evaluation only."""

    def __init__(self):
        self._store = {
            1: Product(1, "Keyboard"),
            2: Product(2, "Mouse"),
            3: Product(3, "Monitor"),
        }

    def query(self, model):
        return _Query(self._store)
