def average_score(scores):
    if not scores:
        return 0
    return sum(scores) / len(scores)


def normalize_score(score):
    if score < 0:
        return 0
    if score > 100:
        return 100
    return score


def grade_user(score):
    normalized = normalize_score(score)
    if normalized >= 90:
        return "A"
    if normalized >= 80:
        return "B"
    if normalized >= 70:
        return "C"
    return "D"
