class MemberRepository:
    def __init__(self):
        self.members = {
            1: {"id": 1, "name": "Alice"},
            2: {"id": 2, "name": "Bob"},
            3: {"id": 3, "name": "Charlie"},
            4: {"id": 4, "name": "Dave"},
        }

    def find_by_id(self, member_id):
        return self.members.get(member_id)

    def find_all_by_ids(self, member_ids):
        return {
            member_id: self.members.get(member_id)
            for member_id in member_ids
        }
