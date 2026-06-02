"""샘플 PR 코드 - 의도적 결함 포함 (N+1, O(n^2))."""


def get_posts(post_ids):
    posts = []
    for pid in post_ids:
        post = db.query(f"SELECT * FROM posts WHERE id={pid}")
        posts.append(post)
    return posts


def calc_discount(price, rate):
    return price * (1 - rate)


def find_dups(items):
    result = []
    for i in items:
        for j in items:
            if i == j:
                result.append(i)
    return result
