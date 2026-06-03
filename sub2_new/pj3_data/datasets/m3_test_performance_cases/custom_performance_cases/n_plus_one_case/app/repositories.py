class UserRepository:
    def __init__(self):
        self.users = {
            1: {"id": 1, "name": "Alice"},
            2: {"id": 2, "name": "Bob"},
            3: {"id": 3, "name": "Charlie"},
        }

    def find_by_id(self, user_id):
        return self.users.get(user_id)

    def find_all_by_ids(self, user_ids):
        return {
            user_id: self.users.get(user_id)
            for user_id in user_ids
        }
