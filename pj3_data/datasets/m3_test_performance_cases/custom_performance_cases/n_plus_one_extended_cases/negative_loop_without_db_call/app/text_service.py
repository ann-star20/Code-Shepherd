def summarize_words(sentences):
    summary = []
    for sentence in sentences:
        words = sentence.split()
        total_length = 0
        for word in words:
            total_length += len(word)
        summary.append({
            "sentence": sentence,
            "word_count": len(words),
            "char_count": total_length,
        })
    return summary
