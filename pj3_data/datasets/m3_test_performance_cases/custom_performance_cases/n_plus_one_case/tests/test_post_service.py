from app.post_service import get_posts_with_authors
from app.repositories import UserRepository


def test_get_posts_with_authors():
    posts = [
        {"id": 1, "title": "hello", "user_id": 1},
        {"id": 2, "title": "world", "user_id": 2},
    ]
    result = get_posts_with_authors(posts, UserRepository())
    assert result[0]["author"] == "Alice"
    assert result[1]["author"] == "Bob"
