class KeywordSearchEngine:
    """In-memory keyword matcher. `query` here is a local string-matching
    helper, NOT a database session/query."""

    def __init__(self, documents):
        self.documents = documents

    def query(self, keyword):
        return [doc for doc in self.documents if keyword in doc]

    def search_all(self, keywords):
        results = []
        for keyword in keywords:
            matches = self.query(keyword)
            results.append({"keyword": keyword, "matches": matches})
        return results
