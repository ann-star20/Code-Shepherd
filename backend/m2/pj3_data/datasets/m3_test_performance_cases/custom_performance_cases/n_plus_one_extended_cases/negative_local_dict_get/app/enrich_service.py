def enrich_posts_with_authors(posts, users_by_id):
    result = []
    for post in posts:
        author = users_by_id.get(post["user_id"])
        result.append({
            "post_id": post["id"],
            "title": post["title"],
            "author": author["name"] if author else None,
        })
    return result
