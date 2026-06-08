def get_posts_with_authors(posts, user_repository):
    result = []
    for post in posts:
        author = user_repository.find_by_id(post["user_id"])
        result.append({
            "post_id": post["id"],
            "title": post["title"],
            "author": author["name"] if author else None,
        })
    return result


def get_posts_with_authors_fixed(posts, user_repository):
    user_ids = {post["user_id"] for post in posts}
    users_by_id = user_repository.find_all_by_ids(user_ids)
    return [
        {
            "post_id": post["id"],
            "title": post["title"],
            "author": users_by_id.get(post["user_id"], {}).get("name"),
        }
        for post in posts
    ]
