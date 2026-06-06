from app.search_engine import KeywordSearchEngine


def test_search_all():
    engine = KeywordSearchEngine(["apple pie", "banana bread", "apple tart"])
    results = engine.search_all(["apple", "banana"])
    assert results[0]["matches"] == ["apple pie", "apple tart"]
    assert results[1]["matches"] == ["banana bread"]
