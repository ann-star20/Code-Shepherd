from app.text_service import summarize_words


def test_summarize_words():
    result = summarize_words(["hello world", "abc"])
    assert result[0]["word_count"] == 2
    assert result[0]["char_count"] == 10
    assert result[1]["word_count"] == 1
    assert result[1]["char_count"] == 3
