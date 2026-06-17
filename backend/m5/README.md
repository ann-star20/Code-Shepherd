# m5 — GraphDB + YouTube (독립 모듈)

**담당 범위**: 별도 문서 업로드 → 엔티티/관계 추출(`doc_id` 필수) → Neo4j 저장, 키워드 기반 YouTube 학습 자료 추천.

Module 1 오케스트레이터와 **분리** — 프론트엔드 또는 업로드 API가 직접 호출.

현재 **스텁** — 계약 엔드포인트만 구현됨.

## 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/health` | 헬스체크 |
| `POST` | `/extract` | LLM 엔티티/관계 추출 → Neo4j |
| `POST` | `/youtube/recommend` | 키워드 기반 YouTube 추천 (MVP) |

## 확장 지점

- `POST /extract`: 문서 본문/메타에서 엔티티·관계 추출 후 Neo4j Aura(또는 compose `neo4j`) upsert
- `POST /youtube/recommend`: 추출 키워드 또는 `doc_id` 연관 태그로 학습 영상 검색
- LangSmith trace: `task_id` / `doc_id` 단위 추적

## 로컬 실행

```bash
# compose 전체 (neo4j + m5 포함)
docker compose up m5 neo4j

curl http://localhost:8006/health
```
