"""RAG 미들웨어 — 사내 컨벤션 검색·코멘트 강화 (정성만, 탐지와 분리).

retriever: Dev1 KMS 검색 API 호출 (직접 DB·임베딩 금지 — 위험 1·2)
augment  : 검색결과 → 코멘트용 rag_context 포맷 (정성 가이드)
"""
