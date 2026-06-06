# Vector DB / 임베딩 학습 노트

**날짜**: 2026-05-22
**복습 예정**: D+1, D+3, D+7

---

## 한 줄 요약
텍스트를 숫자 배열로 변환해서 "비슷한 내용"을 수학적으로 찾을 수 있게 하는 DB.

---

## 1. 비유

**일반 DB 검색** (LIKE 검색):
```
"SQL 인젝션" 검색 → 정확히 "SQL 인젝션"이라는 단어가 있는 것만 찾음
"SQL injection" → 못 찾음 (다른 단어니까)
```

**Vector DB 검색**:
```
"SQL 인젝션" 검색 → 의미가 비슷한 것 찾음
"SQL injection", "쿼리 삽입 취약점", "데이터베이스 공격" 도 찾아줌
```

왜냐하면 텍스트를 **숫자 배열(벡터)**로 변환했을 때
의미가 비슷하면 숫자도 비슷하기 때문.

---

## 2. 개념

**임베딩(Embedding)**: 텍스트 → 숫자 배열로 변환하는 과정

```
"SQL 인젝션" → [0.12, -0.34, 0.89, 0.02, ...]  (1536개 숫자)
"SQL injection" → [0.11, -0.33, 0.91, 0.01, ...]  (비슷한 숫자!)
"오늘 날씨" → [0.92, 0.15, -0.44, 0.77, ...]     (전혀 다른 숫자)
```

**유사도 계산**: 두 벡터가 얼마나 비슷한지 = cosine similarity (0~1, 1에 가까울수록 유사)

**Vector DB (Milvus)**: 이 벡터들을 저장하고 빠르게 검색해주는 DB

---

## 3. 왜 쓰나
Dev 2에서 유사 이슈 검색에 사용:
- **없으면**: "이 이슈 전에도 나왔나?" 를 알 수 없음
- **있으면**: "SQL 인젝션 가능성" 이슈 → 과거에 비슷한 이슈 있었던 PR 번호 + 유사도 반환

---

## 4. 코드 (Dev 2)

```python
# vector_store/similarity.py
from openai import OpenAI
from pymilvus import MilvusClient

openai_client = OpenAI()

# Step 1: 텍스트 → 벡터 변환 (임베딩)
def _get_embedding(text: str) -> list[float]:
    response = openai_client.embeddings.create(
        model="text-embedding-3-small",  # OpenAI 임베딩 모델
        input=text
    )
    return response.data[0].embedding   # [0.12, -0.34, 0.89, ...] 숫자 배열 반환

# Step 2: Milvus에서 유사 벡터 검색
def _search(message: str) -> list[dict]:
    client = MilvusClient(uri="http://localhost:19530")
    embedding = _get_embedding(message)  # 검색어도 벡터로 변환

    results = client.search(
        collection_name="scan_issues",
        data=[embedding],   # 이 벡터와 비슷한 것 찾아줘
        limit=3,            # 상위 3개만
    )

    # distance가 낮을수록 유사 → similarity = 1 - distance
    return [
        {"pr_id": hit.entity["pr_id"], "similarity": round(1 - hit.distance, 3)}
        for hit in results[0]
        if 1 - hit.distance > 0.85  # 85% 이상 유사한 것만
    ]
```

**결과 예시:**
```json
[
  { "pr_id": "98", "date": "2026-04-10", "similarity": 0.94 },
  { "pr_id": "75", "date": "2026-03-22", "similarity": 0.89 }
]
```
→ "PR #98에서 94% 유사한 이슈가 있었음" 이라는 인사이트 제공

---

## 복습 퀴즈

1. Q: 임베딩(Embedding)이란?
   A: (텍스트를 숫자 배열(벡터)로 변환하는 것. 의미가 비슷하면 숫자도 비슷해짐)

2. Q: 일반 LIKE 검색과 Vector DB 검색의 차이는?
   A: (LIKE는 정확한 단어 일치. Vector DB는 의미 유사도로 검색)

3. Q: Dev 2에서 Milvus를 쓰는 목적은?
   A: (과거 유사 이슈 검색 — "이 패턴 전에도 나왔나?")
