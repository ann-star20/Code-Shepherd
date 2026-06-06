def find_duplicate_pairs(users):
    duplicates = []
    for left in users:
        for right in users:
            if left["id"] == right["id"]:
                continue
            if left["email"] == right["email"]:
                duplicates.append((left["id"], right["id"]))
    return duplicates


def find_duplicate_pairs_fixed(users):
    seen = {}
    duplicates = []
    for user in users:
        email = user["email"]
        if email in seen:
            duplicates.append((seen[email], user["id"]))
        else:
            seen[email] = user["id"]
    return duplicates
