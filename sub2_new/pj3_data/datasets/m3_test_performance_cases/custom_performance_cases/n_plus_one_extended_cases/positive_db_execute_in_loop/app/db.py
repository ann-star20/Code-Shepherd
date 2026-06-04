class FakeCursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class FakeDB:
    def __init__(self):
        self.invoices = {
            1: {"total": 100},
            2: {"total": 250},
            3: {"total": 50},
        }

    def execute(self, query, params=()):
        invoice_id = params[0] if params else None
        return FakeCursor(self.invoices.get(invoice_id))
