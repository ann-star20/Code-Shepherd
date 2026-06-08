## 🤖 자동 리뷰 (lgtm · Major 1 · Minor 1)

### 🟡 Major: PERF-002 (src/posts.py:8)
N+1 쿼리: 루프 안에서 DB 호출이 반복됩니다.

💡 joinedload()/selectinload() 등으로 루프 밖에서 조회하세요.

### 🔵 Minor: PERF-001 (src/posts.py:21)
O(n^2) 시간복잡도: 2중 중첩 루프가 감지되었습니다.

💡 루프를 평탄화하거나 적절한 자료구조로 복잡도를 낮추세요.