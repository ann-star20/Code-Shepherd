# Q&A — 유사 이슈 검색 (vector_search 노드)

**날짜**: 2026-05-29

---

## Q. 유사 이슈 검색은 어떻게 해? 유사 데이터가 없는데?

**A.** 지금은 pgVector에 데이터가 없어서 유사 이슈 검색이 안 됩니다. 하지만 파이프라인은 정상 동작합니다.

---

## 현재 상태

```
vector_search 노드 실행
    │
    ▼
pgVector(chunk_embeddings) 조회
    │
    ▼
결과 0건 → 빈 리스트 [] 반환 (에러 없이 그냥 넘어감)
    │
    ▼
llm_judge 노드로 전달 (유사 이슈 없이 LLM 판단만)
```

유사 이슈 없이도 파이프라인은 정상 동작합니다. 단지 `similar_issues: []`로 저장될 뿐.

---

## 데이터가 생기는 시점

스캔을 할수록 자동으로 쌓입니다.

```
1회차 스캔 → 결과 DB 저장 → chunk_embeddings에 임베딩 저장
2회차 스캔 → 1회차 결과가 유사 이슈로 검색됨
3회차 스캔 → 1, 2회차 결과 검색됨
...반복
```

---

## 지금 당장 테스트하려면 — seed 데이터 직접 넣기

Week 5 데모 전에 `chunk_embeddings`에 샘플 데이터를 수동으로 INSERT할 수 있습니다.
(CLAUDE.md §8 명시)

```sql
INSERT INTO chunk_embeddings (chunk_id, embedding, content, metadata)
VALUES (
  gen_random_uuid(),
  '[0.1, 0.2, ...]'::vector(4096),
  'SQL 인젝션 방지: 파라미터화된 쿼리 사용...',
  '{"category": "보안", "doc_title": "SQL 인젝션 방지 패턴"}'::jsonb
);
```

단, chunk_embeddings에 실제 문서를 적재하는 것은 **Dev1(KMS)** 담당입니다.
Dev2 혼자 완성할 수 없는 부분입니다.

---

## 상황별 동작 정리

| 상황 | 동작 |
|------|------|
| 지금 (데이터 없음) | `similar_issues: []` — 파이프라인은 정상 동작 |
| 스캔 누적 후 | 과거 이슈 자동 검색됨 |
| Week 5 Dev1 연동 후 | KMS 문서도 유사 이슈로 검색됨 |

**결론**: 지금은 데이터 없어도 됩니다. 스캔이 쌓이면 자동으로 됩니다.
