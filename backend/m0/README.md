# m0 — KMS 인제스트 스텁

**담당 범위**: 사내 문서(PDF/DOCX/PPTX/TXT) → Markdown 변환 → 청킹 → pgVector 저장.

현재는 **스텁** — `/health` + `/ingest` 계약 엔드포인트만 구현됨.

## 확장 지점

`app/main.py`의 `ingest()` 함수를 실제 파이프라인으로 교체:
1. UnStructured.io로 문서 파싱 → Markdown 변환
2. Markdown 검증 (품질 점수 ≥ 0.8)
3. Parent/Child 청킹
4. pgVector 저장

## Alembic

빈 골격 — m0 담당자가 필요한 테이블 스키마를 추가한다.
`users`, `teams` 등 공통 테이블은 `api-core` alembic 소유 (FK만 참조).

## 실행

```bash
docker compose up m0
```

## 테스트

```bash
uv run pytest tests/
```
