class CustomerRepository:
    def __init__(self):
        self.customers = {
            1: {"id": 1, "name": "Alice"},
            2: {"id": 2, "name": "Bob"},
            3: {"id": 3, "name": "Charlie"},
        }

    def find_by_id(self, customer_id):
        return self.customers.get(customer_id)

    def find_all_by_ids(self, customer_ids):
        return {
            customer_id: self.customers.get(customer_id)
            for customer_id in customer_ids
        }
