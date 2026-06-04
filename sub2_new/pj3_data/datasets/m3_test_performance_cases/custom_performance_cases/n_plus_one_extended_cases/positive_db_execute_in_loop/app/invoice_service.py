def load_invoice_totals(invoice_ids, db):
    totals = []
    for invoice_id in invoice_ids:
        row = db.execute(
            "SELECT total FROM invoices WHERE id = ?", (invoice_id,)
        ).fetchone()
        totals.append(row["total"] if row else 0)
    return totals
