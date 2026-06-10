from app.enrich_service import enrich_posts_with_authors


def test_enrich_posts_with_authors():
    users_by_id = {
        1: {"id": 1, "name": "Alice"},
        2: {"id": 2, "name": "Bob"},
    }
    posts = [
        {"id": 1, "title": "hello", "user_id": 1},
        {"id": 2, "title": "world", "user_id": 2},
    ]
    result = enrich_posts_with_authors(posts, users_by_id)
    assert result[0]["author"] == "Alice"
    assert result[1]["author"] == "Bob"
